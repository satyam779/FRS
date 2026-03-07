# ================= IMPORTS =================
import os
import csv
import json
import pickle
import base64
import binascii
import io
import threading
import stat
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request,
    redirect, session, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash

import face_recognition
import numpy as np
from PIL import Image, UnidentifiedImageError

# ================= CONFIG =================
DATA_DIR = os.path.abspath(os.environ.get("DATA_DIR", "."))
ENC_FILE = os.path.join(DATA_DIR, "known_faces_encodings.pkl")
KNOWN_DIR = os.path.join(DATA_DIR, "known_faces")
ATTEND_DIR = os.path.join(DATA_DIR, "attendance")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

TOLERANCE = 0.43
ENROLL_SAMPLES = 5
DUPLICATE_CHECK_MINUTES = 3

os.makedirs(KNOWN_DIR, exist_ok=True)
os.makedirs(ATTEND_DIR, exist_ok=True)

encoding_lock = threading.RLock()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "attendance_secure_key")

# ================= USERS =================
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# Auto-create admin
if not os.path.exists(USERS_FILE):
    save_users({
        "admin": {
            "password": generate_password_hash("admin123"),
            "role": "admin"
        }
    })

# ================= LOGIN REQUIRED =================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

# ================= ENCODING LOAD =================
def load_encodings():
    if os.path.exists(ENC_FILE):
        try:
            with open(ENC_FILE, "rb") as f:
                data = pickle.load(f)
                return data.get("encodings", []), data.get("names", [])
        except:
            return [], []
    return [], []

def save_encodings(encodings, names):
    with encoding_lock:
        with open(ENC_FILE, "wb") as f:
            pickle.dump({"encodings": encodings, "names": names}, f)

known_encodings, known_names = load_encodings()

def reload_encodings():
    global known_encodings, known_names
    known_encodings, known_names = load_encodings()

def list_enrolled_people():
    reload_encodings()
    return sorted(set(known_names), key=str.lower)

def safe_remove_tree(path):
    if not os.path.exists(path):
        return

    import shutil

    def handle_remove_readonly(func, target_path, exc_info):
        # Windows can keep files read-only; clear bit and retry once.
        os.chmod(target_path, stat.S_IWRITE)
        func(target_path)

    shutil.rmtree(path, onerror=handle_remove_readonly)

def decode_base64_image(image_data):
    if not image_data:
        raise ValueError("Missing image data")

    if "," in image_data:
        image_data = image_data.split(",", 1)[1]

    # Form-encoded payloads can convert '+' to spaces.
    normalized = image_data.strip().replace(" ", "+")

    # Pad to valid base64 length when clients omit trailing '='.
    padding = len(normalized) % 4
    if padding:
        normalized += "=" * (4 - padding)

    img_bytes = base64.b64decode(normalized, validate=False)
    return Image.open(io.BytesIO(img_bytes)).convert("RGB")

# ================= ROUTES =================

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        users = load_users()
        username = request.form["username"]
        password = request.form["password"]

        if username in users and check_password_hash(users[username]["password"], password):
            session["user"] = username
            session["role"] = users[username]["role"]
            return redirect("/dashboard")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/faces")
@login_required
def faces():
    users = list_enrolled_people()
    return render_template("faces.html", users=users)

# ================= FACE MATCH =================
def match_face(face_encoding):
    reload_encodings()

    if len(known_encodings) == 0:
        return None, None

    distances = face_recognition.face_distance(known_encodings, face_encoding)
    best_index = np.argmin(distances)
    best_distance = distances[best_index]

    if best_distance > TOLERANCE:
        return None, None

    confidence = int((1 - best_distance) * 100)
    return known_names[best_index], confidence

@app.route("/add_face", methods=["GET", "POST"])
@login_required
def add_face():
    global known_encodings, known_names

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        file = request.files.get("image")

        if not name or not file:
            return "Name and image required"

        try:
            img = Image.open(file).convert("RGB")
            img = img.resize((640, 480))  # Resize for speed
        except:
            return "Invalid image"

        # FAST encoding (remove num_jitters)
        encodings = face_recognition.face_encodings(np.array(img))

        if not encodings:
            return "No face detected"

        person_dir = os.path.join(KNOWN_DIR, name)
        os.makedirs(person_dir, exist_ok=True)

        img.save(os.path.join(person_dir, "profile.jpg"))

        with encoding_lock:
            known_encodings.append(encodings[0])
            known_names.append(name)
            save_encodings(known_encodings, known_names)

        return redirect("/faces")

    return render_template("add_face.html")

# ================= WEBCAM ENROLL PAGE =================
@app.route("/webcam_enroll", methods=["GET", "POST"])
@login_required
def webcam_enroll():
    global known_encodings, known_names

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or request.form.get("name", "")).strip()
        image_data = data.get("image") or request.form.get("image")

        if not name or not image_data:
            return jsonify({"status": "MISSING_DATA"})

        try:
            img = decode_base64_image(image_data)
        except (binascii.Error, ValueError, UnidentifiedImageError):
            return jsonify({"status": "BAD_IMAGE"})

        encodings = face_recognition.face_encodings(np.array(img))

        if not encodings:
            return jsonify({"status": "NO_FACE"})

        count = known_names.count(name)

        person_dir = os.path.join(KNOWN_DIR, name)
        os.makedirs(person_dir, exist_ok=True)
        img.save(os.path.join(person_dir, f"img_{count+1}.jpg"))

        with encoding_lock:
            known_encodings.append(encodings[0])
            known_names.append(name)
            save_encodings(known_encodings, known_names)

        count += 1

        if count >= ENROLL_SAMPLES:
            return jsonify({
                "status": "ENROLL_COMPLETE",
                "name": name
            })

        return jsonify({
            "status": "ENROLLING",
            "count": count
        })

    return render_template("webcam_enroll.html")

# ================= DELETE FACE =================
@app.route("/delete/<path:name>")
@login_required
def delete_face(name):
    return _delete_face_by_name(name)

@app.route("/delete_face", methods=["POST"])
@login_required
def delete_face_post():
    name = request.form.get("name", "").strip()
    if not name:
        return redirect("/faces")
    return _delete_face_by_name(name)

def _delete_face_by_name(name):
    global known_encodings, known_names

    with encoding_lock:
        indices = [i for i, n in enumerate(known_names) if n == name]
        for i in sorted(indices, reverse=True):
            known_encodings.pop(i)
            known_names.pop(i)
        save_encodings(known_encodings, known_names)

    try:
        safe_remove_tree(os.path.join(KNOWN_DIR, name))
    except OSError:
        # Keep UI functional even if folder cleanup fails.
        pass

    attendance_file = os.path.join(ATTEND_DIR, f"{name}.csv")
    if os.path.exists(attendance_file):
        try:
            os.remove(attendance_file)
        except OSError:
            pass

    return redirect("/faces")

# ================= DUPLICATE CHECK =================
def duplicate_recent(name, entry=None):
    file_path = os.path.join(ATTEND_DIR, f"{name}.csv")
    if not os.path.exists(file_path):
        return False

    with open(file_path, "r") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return False

    last = rows[-1]
    last_status = (last.get("Status") or "").upper()
    if entry and last_status and last_status != entry:
        return False

    last_time = datetime.strptime(
        f"{last['Date']} {last['Time']}",
        "%Y-%m-%d %H:%M:%S"
    )

    return datetime.now() - last_time < timedelta(minutes=DUPLICATE_CHECK_MINUTES)

def ensure_attendance_schema(file_path):
    if not os.path.exists(file_path):
        return

    with open(file_path, "r", newline="") as f:
        rows = list(csv.reader(f))

    if not rows:
        return

    header = rows[0]
    if header == ["Date", "Time", "Status"]:
        return

    # Migrate old schema Date,Time -> Date,Time,Status
    if header[:2] != ["Date", "Time"]:
        return

    migrated = [["Date", "Time", "Status"]]
    day_next_status = {}

    for row in rows[1:]:
        if len(row) < 2:
            continue
        date = row[0]
        time = row[1]
        status = day_next_status.get(date, "IN")
        day_next_status[date] = "OUT" if status == "IN" else "IN"
        migrated.append([date, time, status])

    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(migrated)

# ================= WEBCAM PAGE =================
@app.route("/webcam")
@login_required
def webcam():
    return render_template("webcam.html")

# ================= WEBCAM ATTEND =================
@app.route("/webcam_attend", methods=["POST"])
@login_required
def webcam_attend():
    data = request.get_json(silent=True) or {}
    image_data = data.get("image", "")
    entry = str(data.get("entry", "")).upper().strip()

    if not image_data:
        return jsonify({"status": "NO_IMAGE"})
    if entry not in {"IN", "OUT"}:
        return jsonify({"status": "INVALID_ENTRY"})

    try:
        img = decode_base64_image(image_data)
    except (binascii.Error, ValueError, UnidentifiedImageError):
        return jsonify({"status": "BAD_IMAGE"})

    enc = face_recognition.face_encodings(np.array(img))

    if not enc:
        return jsonify({"status": "NO_FACE"})

    name, confidence = match_face(enc[0])
    if not name:
        return jsonify({"status": "UNKNOWN"})

    file_path = os.path.join(ATTEND_DIR, f"{name}.csv")
    ensure_attendance_schema(file_path)
    if duplicate_recent(name, entry):
        return jsonify({"status": "ALREADY_MARKED", "name": name, "entry": entry})

    now = datetime.now()

    with open(file_path, "a", newline="") as f:
        writer = csv.writer(f)
        if os.stat(file_path).st_size == 0:
            writer.writerow(["Date", "Time", "Status"])
        writer.writerow([now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), entry])

    return jsonify({
        "status": "ATTENDANCE_MARKED",
        "name": name,
        "confidence": confidence,
        "entry": entry
    })

# ================= ATTENDANCE LIST =================
@app.route("/attendance")
@login_required
def attendance_list():
    persons = [f.replace(".csv", "") for f in os.listdir(ATTEND_DIR) if f.endswith(".csv")]
    return render_template("attendance_list.html", persons=persons)

@app.route("/attendance/<name>")
@login_required
def attendance_person(name):
    file_path = os.path.join(ATTEND_DIR, f"{name}.csv")
    records = []

    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            rows = list(csv.DictReader(f))

        grouped = {}
        for r in rows:
            date = r.get("Date")
            time = r.get("Time")
            status = str(r.get("Status", "")).upper()
            if not date or not time:
                continue

            if date not in grouped:
                grouped[date] = {"Date": date, "In": "--", "Out": "--"}

            if status in {"IN", "OUT"}:
                if status == "IN":
                    if grouped[date]["In"] == "--":
                        grouped[date]["In"] = time
                else:
                    grouped[date]["Out"] = time
            else:
                # Backward compatibility for old rows without Status.
                if grouped[date]["In"] == "--":
                    grouped[date]["In"] = time
                else:
                    grouped[date]["Out"] = time

        for d in grouped.values():
            if d["In"] != "--" and d["Out"] != "--":
                t1 = datetime.strptime(d["In"], "%H:%M:%S")
                t2 = datetime.strptime(d["Out"], "%H:%M:%S")
                diff = t2 - t1
                d["Work"] = f"{diff.seconds//3600}h {(diff.seconds%3600)//60}m"
            else:
                d["Work"] = "--"
            records.append(d)

    return render_template("attendance_person.html", name=name, records=records)

# ================= EXPORT =================
@app.route("/export/<name>")
@login_required
def export_csv(name):
    file_path = os.path.join(ATTEND_DIR, f"{name}.csv")
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "No records", 404

# ================= USERS =================
@app.route("/users", methods=["GET", "POST"])
@login_required
def manage_users():
    if session.get("role") != "admin":
        return "Access denied", 403

    users = load_users()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        raw_password = request.form.get("password", "").strip()

        if not username or not raw_password:
            return render_template("users.html", users=users, error="Username and password are required.")

        if username in users:
            return render_template("users.html", users=users, error="User already exists.")

        password = generate_password_hash(raw_password)
        users[username] = {"password": password, "role": "user"}
        save_users(users)

    return render_template("users.html", users=users)

@app.route("/delete_user/<username>")
@login_required
def delete_user(username):
    if session.get("role") != "admin":
        return "Access denied", 403

    if username == session.get("user"):
        return redirect("/users")

    users = load_users()

    # Keep at least one admin account.
    if users.get(username, {}).get("role") == "admin":
        admin_count = sum(1 for u in users.values() if u.get("role") == "admin")
        if admin_count <= 1:
            return redirect("/users")

    users.pop(username, None)
    save_users(users)
    return redirect("/users")

# ================= RUN =================
if __name__ == "__main__":
    print("\n====== REGISTERED ROUTES ======")
    for rule in app.url_map.iter_rules():
        print(rule)
    print("================================\n")

    app.run(debug=True, host="0.0.0.0", port=5000)
