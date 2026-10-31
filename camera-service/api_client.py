import requests
import base64
import logging
import tempfile
import os
from datetime import date, time
from config import API_BASE_URL, BACKEND_UPLOADS_URL, CAMERA_SERVICE_EMAIL, CAMERA_SERVICE_PASSWORD

logger = logging.getLogger("api_client")

_token: str = ""


def login() -> bool:
    """Authenticate with the backend and cache the JWT token."""
    global _token
    try:
        r = requests.post(
            f"{API_BASE_URL}/auth/login",
            data={"username": CAMERA_SERVICE_EMAIL, "password": CAMERA_SERVICE_PASSWORD},
            timeout=10,
        )
        r.raise_for_status()
        _token = r.json()["access_token"]
        logger.info("Authenticated with backend API")
        return True
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return False


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_token}"}


def _get(url: str, **kwargs):
    """GET with auth; re-login once on 401."""
    global _token
    r = requests.get(url, headers=_auth_headers(), timeout=10, **kwargs)
    if r.status_code == 401:
        logger.warning("Token expired — re-authenticating")
        login()
        r = requests.get(url, headers=_auth_headers(), timeout=10, **kwargs)
    r.raise_for_status()
    return r


def _post(url: str, **kwargs):
    """POST with auth; re-login once on 401."""
    global _token
    r = requests.post(url, headers=_auth_headers(), timeout=10, **kwargs)
    if r.status_code == 401:
        logger.warning("Token expired — re-authenticating")
        login()
        r = requests.post(url, headers=_auth_headers(), timeout=10, **kwargs)
    r.raise_for_status()
    return r


def download_photo(db_path: str) -> str | None:
    """
    Download a student photo from the backend to a local temp file.
    db_path is the relative path stored in the DB, e.g. 'uploads/1/abc.jpg'.
    Returns the local temp file path, or None on failure.
    """
    # Build the full download URL
    # db_path is like "uploads/1/abc.jpg" — strip leading "uploads/" if present
    relative = db_path.lstrip("/")
    if relative.startswith("uploads/"):
        relative = relative[len("uploads/"):]

    url = f"{BACKEND_UPLOADS_URL}/{relative}"
    try:
        r = requests.get(url, headers=_auth_headers(), timeout=30)
        if r.status_code == 401:
            login()
            r = requests.get(url, headers=_auth_headers(), timeout=30)
        r.raise_for_status()

        ext = os.path.splitext(db_path)[1] or ".jpg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tmp.write(r.content)
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.warning(f"Could not download photo {url}: {e}")
        return None


def get_students_pending_enrollment():
    """Return students who have photos but no embeddings."""
    try:
        return _get(f"{API_BASE_URL}/students/camera/pending-enrollment").json()
    except Exception as e:
        logger.error(f"Failed to fetch pending enrollments: {e}")
        return []


def post_embeddings(student_id: int, embeddings: list):
    """Store computed face embeddings for a student."""
    try:
        _post(f"{API_BASE_URL}/students/{student_id}/embeddings", json=embeddings)
        logger.info(f"Stored {len(embeddings)} embeddings for student {student_id}")
    except Exception as e:
        logger.error(f"Failed to store embeddings for student {student_id}: {e}")


def get_all_enrolled_students():
    """Return enrolled students with face embeddings for the recognizer."""
    try:
        return _get(f"{API_BASE_URL}/students/camera/enrolled").json()
    except Exception as e:
        logger.error(f"Failed to fetch enrolled students: {e}")
        return []


def check_school_day(today: date) -> bool:
    """Return False if today is a holiday/non-school day."""
    try:
        cal = _get(f"{API_BASE_URL}/calendar/").json()
        for entry in cal:
            if entry.get("date") == str(today) and entry.get("is_active"):
                logger.info(f"Today is a non-school day: {entry.get('label')}")
                return False
        return True
    except Exception as e:
        logger.error(f"Failed to check calendar: {e}")
        return True  # Default to school day if can't reach API


def post_late_entry(
    student_id,
    house_id,
    arrival_time: time,
    entry_date: date,
    confidence: float,
    image_bytes: bytes = None,
):
    payload = {
        "student_id": student_id,
        "house_id": house_id,
        "arrival_time": arrival_time.strftime("%H:%M:%S"),
        "date": str(entry_date),
        "confidence_score": round(confidence, 4),
    }
    if image_bytes:
        payload["captured_image_b64"] = base64.b64encode(image_bytes).decode()

    try:
        result = _post(f"{API_BASE_URL}/late-entries/from-recognition", json=payload).json()
        logger.info(f"Posted late entry: student={student_id} → {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to post late entry: {e}")
        return None
