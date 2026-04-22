# Face Recognition System (FRS)

A Flask-based face recognition attendance system.

## Setup Instructions for Collaborators

To run this project on a new machine, follow these steps:

### 1. Prerequisites
- Python 3.14 (or compatible)
- CMake (required for building `dlib`)
- Visual Studio C++ Build Tools (required for `dlib` on Windows)

### 2. Clone the Repository
```bash
git clone https://github.com/satyam779/FRS.git
cd FRS
```

### 3. Create a Virtual Environment
Never use someone else's `venv` folder as it contains absolute paths. Create your own:
```powershell
python -m venv venv
```

### 4. Activate the Environment
- **Windows**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **Mac/Linux**:
  ```bash
  source venv/bin/activate
  ```

### 5. Install Dependencies
```bash
pip install -r requirements.txt
```

*Note: If you are on Windows and `dlib` fails to install, you may need to install it from a pre-compiled wheel or ensure you have the C++ Build Tools installed.*

### 6. Run the Server
```bash
python server.py
```

### 7. Access the Dashboard
Open [http://127.0.0.1:5000/dashboard](http://127.0.0.1:5000/dashboard)

- **Default User**: `admin`
- **Default Pass**: `admin123`

## Project Structure
- `server.py`: Main Flask application.
- `known_faces/`: Stores enrolled face images (ignored by git).
- `attendance/`: Stores attendance CSV logs (ignored by git).
- `users.json`: User credentials.
