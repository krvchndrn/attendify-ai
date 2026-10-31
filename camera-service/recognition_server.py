"""
Attendify.ai Recognition Server
================================
Lightweight HTTP server that the browser scan page POSTs images to.
Runs the face_recognition pipeline locally and returns match results.

Also handles face enrollment: downloads student photos from the Railway
backend, computes embeddings locally, and stores them back via the API.

Usage (inside camera-service/):
    cp .env.example .env          # fill in API_BASE_URL and credentials
    pip install -r requirements.txt
    python recognition_server.py

Listens on http://localhost:8001

Endpoints:
  GET  /health            — liveness check + enrolled count
  POST /enroll            — process all pending-enrollment students
  POST /reload            — reload face DB from API
  POST /recognize         — recognize faces in a base64 image
"""

import base64
import io
import os
import logging
import tempfile
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
import face_recognition
from PIL import Image

import config
import api_client
from api_client import download_photo
from detector import FaceEnroller, FaceRecognizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("recognition_server")

app = Flask(__name__)
CORS(app)

recognizer = FaceRecognizer(confidence_threshold=config.CONFIDENCE_THRESHOLD)


def run_enrollment() -> list:
    """
    Process all students with photos but no face embeddings.
    Downloads photos from the Railway backend, encodes them locally,
    and posts the embeddings back to the API.
    """
    pending = api_client.get_students_pending_enrollment()
    if not pending:
        logger.info("No students pending enrollment.")
        return []

    enroller = FaceEnroller()
    results = []
    tmp_files = []

    for student in pending:
        sid = student["id"]
        name = student.get("name", f"ID {sid}")
        db_paths = student.get("photo_paths") or []

        logger.info(f"Enrolling {name}: downloading {len(db_paths)} photo(s)...")

        # Download each photo to a temp file
        local_paths = []
        for db_path in db_paths:
            local = download_photo(db_path)
            if local:
                local_paths.append(local)
                tmp_files.append(local)
            else:
                logger.warning(f"  Could not download: {db_path}")

        if not local_paths:
            logger.warning(f"  {name}: no photos could be downloaded — skipping")
            results.append({"id": sid, "name": name, "vectors": 0, "error": "photos not downloadable"})
            continue

        encodings = enroller.enroll(local_paths)
        if not encodings:
            logger.warning(f"  {name}: no faces detected in downloaded photos")
            results.append({"id": sid, "name": name, "vectors": 0, "error": "no face detected"})
            continue

        api_client.post_embeddings(sid, encodings)
        logger.info(f"  {name}: {len(encodings)} face vector(s) stored")
        results.append({"id": sid, "name": name, "vectors": len(encodings)})

    # Clean up temp files
    for f in tmp_files:
        try:
            os.unlink(f)
        except Exception:
            pass

    return results


def reload_students():
    students = api_client.get_all_enrolled_students()
    recognizer.load_students(students)
    logger.info(
        f"Reloaded: {len(recognizer.known_encodings)} face vectors "
        f"across {len(recognizer._info)} students"
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "enrolled_students": len(recognizer._info),
        "face_vectors": len(recognizer.known_encodings),
        "api_base": config.API_BASE_URL,
        "uploads_url": config.BACKEND_UPLOADS_URL,
    })


@app.route("/enroll", methods=["POST"])
def enroll():
    """Process all pending-enrollment students and reload recognizer."""
    logger.info("Enrollment triggered via API")
    try:
        results = run_enrollment()
        if results:
            reload_students()
        enrolled = [r for r in results if r.get("vectors", 0) > 0]
        failed = [r for r in results if r.get("vectors", 0) == 0]
        return jsonify({
            "status": "ok",
            "processed": len(results),
            "enrolled": len(enrolled),
            "failed": len(failed),
            "results": results,
        })
    except Exception as e:
        logger.error(f"Enrollment error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/reload", methods=["POST"])
def reload():
    """Reload face embeddings from the API (no new encoding)."""
    try:
        reload_students()
        return jsonify({
            "status": "ok",
            "enrolled_students": len(recognizer._info),
            "face_vectors": len(recognizer.known_encodings),
        })
    except Exception as e:
        logger.error(f"Reload error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/recognize", methods=["POST"])
def recognize():
    """
    Recognize faces in a base64-encoded image.
    Body: {"image_b64": "<base64 JPEG/PNG>"}
    Returns: {"face_count": N, "detections": [...]}
    """
    data = request.get_json(silent=True)
    if not data or "image_b64" not in data:
        return jsonify({"error": "Missing image_b64 field"}), 400

    try:
        img_bytes = base64.b64decode(data["image_b64"])
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        frame = np.array(img)
    except Exception as e:
        return jsonify({"error": f"Invalid image: {e}"}), 400

    try:
        detections = recognizer.recognize_all(frame)
        return jsonify({
            "face_count": len(detections),
            "detections": detections,
        })
    except Exception as e:
        logger.error(f"Recognition failed: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Attendify.ai Recognition Server")
    logger.info(f"  API:     {config.API_BASE_URL}")
    logger.info(f"  Photos:  {config.BACKEND_UPLOADS_URL}")
    logger.info("=" * 60)

    if not api_client.login():
        logger.error("Cannot authenticate with backend — check .env credentials")
        raise SystemExit(1)

    logger.info("Processing any pending enrollments on startup...")
    results = run_enrollment()
    enrolled_count = len([r for r in results if r.get("vectors", 0) > 0])
    if results:
        logger.info(f"Startup enrollment: {enrolled_count}/{len(results)} students enrolled")

    reload_students()

    logger.info("Starting server on http://localhost:8001")
    app.run(host="0.0.0.0", port=8001, debug=False, use_reloader=False)
