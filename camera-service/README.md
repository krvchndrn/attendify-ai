# Attendify.ai — Camera Service

Runs on the **school gate computer** (Raspberry Pi, laptop, or any machine with a webcam).  
Connects to the Railway-hosted backend over HTTPS — no local database needed.

---

## Quick Start

### 1. Prerequisites

- Python 3.10 or 3.11 (not 3.12 — dlib wheels aren't available yet)
- A webcam connected and working (`ls /dev/video*`)
- `cmake` and `libboost` installed (needed to compile dlib):

```bash
# Ubuntu / Raspberry Pi OS
sudo apt-get update
sudo apt-get install -y cmake libboost-python-dev libopenblas-dev

# macOS
brew install cmake boost
```

### 2. Install

```bash
cd camera-service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```
API_BASE_URL=https://backend-production-1348.up.railway.app/api/v1
BACKEND_UPLOADS_URL=https://backend-production-1348.up.railway.app/uploads
CAMERA_SERVICE_EMAIL=admin@attendify.ai
CAMERA_SERVICE_PASSWORD=admin123
SCHOOL_START_TIME=08:30
```

### 4. Run

**Gate camera mode** (starts scanning after school start time):
```bash
source venv/bin/activate
python main.py
```

**Enrollment only** (compute face embeddings for newly-uploaded students, then exit):
```bash
python main.py --enroll-only
```

**Recognition server** (HTTP API on port 8001, for the browser-based scan page):
```bash
python recognition_server.py
```

---

## How It Works

### Enrollment Flow

1. Admin adds a student via the web UI and uploads ≥3 photos.
2. Camera service downloads those photos from Railway (`/uploads/…`).
3. `face_recognition` encodes each photo into a 128-dimension vector.
4. Vectors are posted back to the API (`POST /students/{id}/embeddings`).
5. Student is now "enrolled" — ready for real-time recognition.

### Gate Scan Loop

1. Waits until `SCHOOL_START_TIME`.
2. Grabs a frame from the camera every `SCAN_INTERVAL_SECONDS`.
3. Runs face recognition against all enrolled students.
4. If a match is found with confidence ≥ threshold, posts a late entry.
5. Each student is only logged once per day.
6. Reloads the face database every 5 minutes (picks up new enrollments).

### Recognition Server (port 8001)

Alternative to the gate camera. Accepts POST requests with a base64-encoded
image and returns match results. Use this if you want to scan from a browser
tab or a mobile device instead of a dedicated Raspberry Pi.

```bash
# Check status
curl http://localhost:8001/health

# Trigger enrollment
curl -X POST http://localhost:8001/enroll

# Reload face DB
curl -X POST http://localhost:8001/reload
```

---

## Confidence Thresholds

| Value | Meaning |
|-------|---------|
| ≥ 0.6 | `auto_confirmed` — logged automatically, points deducted |
| 0.4–0.6 | `needs_review` — queued for teacher confirmation |
| < 0.4 | rejected — face too unclear, not logged |

Adjust with `CONFIDENCE_THRESHOLD` in `.env`.
