# Deploy Guide (Face Attendance)

## 1) One-time prep

- Push this project to GitHub.
- Make sure these files are in repo root:
  - `Dockerfile`
  - `requirements.txt`
  - `wsgi.py`

## 2) Deploy on Render (recommended)

1. In Render dashboard, create `New +` -> `Web Service`.
2. Connect your GitHub repo.
3. Environment: `Docker`.
4. Add environment variables:
   - `SECRET_KEY` = strong random string
   - `DATA_DIR` = `/data`
5. Add a persistent disk and mount path `/data`.
6. Deploy.

Notes:
- Webcam access in browser requires HTTPS. Render gives HTTPS by default.
- If you do not mount a disk, faces/attendance/users will be lost on restart.

## 3) Local Docker test

```bash
docker build -t frs-app .
docker run --rm -p 5000:5000 -e SECRET_KEY=change-me -e DATA_DIR=/app/data -v frs_data:/app/data frs-app
```

Open `http://127.0.0.1:5000`.

## 4) Login

- Default admin user is auto-created on first run:
  - Username: `admin`
  - Password: `admin123`
- Change this password immediately after first login.
