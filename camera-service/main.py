"""
Attendify.ai Camera Service
============================
Runs at the school gate camera (Raspberry Pi or any PC with a webcam).

On start:
  1. Authenticates with the Railway backend.
  2. Downloads photos for any students pending face enrollment, encodes them,
     and stores embeddings back in the backend.
  3. Loads all enrolled students' face embeddings into memory.
  4. Opens the camera and scans for late students after school start time.

Usage:
    cp .env.example .env          # fill in API_BASE_URL and credentials
    pip install -r requirements.txt
    python main.py                # full gate-camera mode
    python main.py --enroll-only  # enrollment only, then exit
"""

import cv2
import time
import logging
import argparse
import os
import sys
import tempfile
from datetime import datetime, date

import config
from detector import FaceEnroller, FaceRecognizer
import api_client
from api_client import (
    download_photo,
    get_students_pending_enrollment,
    post_embeddings,
    get_all_enrolled_students,
    check_school_day,
    post_late_entry,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("camera_service")

RELOAD_INTERVAL_SECONDS = 300  # Reload face DB every 5 minutes


def run_enrollment():
    """
    Download photos for students pending enrollment, compute embeddings locally,
    and store them back in the backend API.
    """
    logger.info("Checking for students pending face enrollment...")
    pending = get_students_pending_enrollment()

    if not pending:
        logger.info("No students pending enrollment.")
        return

    enroller = FaceEnroller()
    for student in pending:
        sid = student["id"]
        name = student.get("name", f"ID {sid}")
        db_paths = student.get("photo_paths") or []

        logger.info(f"Enrolling {name}: downloading {len(db_paths)} photo(s)...")

        tmp_files = []
        local_paths = []
        for db_path in db_paths:
            local = download_photo(db_path)
            if local:
                local_paths.append(local)
                tmp_files.append(local)
            else:
                logger.warning(f"  Could not download {db_path}")

        try:
            if not local_paths:
                logger.warning(f"  {name}: no downloadable photos — skipping")
                continue

            encodings = enroller.enroll(local_paths)
            if not encodings:
                logger.warning(f"  {name}: no faces detected — skipping")
                continue

            post_embeddings(sid, encodings)
            logger.info(f"  Enrolled {name}: {len(encodings)} face vector(s) stored")
        finally:
            for f in tmp_files:
                try:
                    os.unlink(f)
                except Exception:
                    pass


def run_camera(recognizer: FaceRecognizer):
    """Open camera and scan for late students."""
    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    if not cap.isOpened():
        logger.error(f"Cannot open camera at index {config.CAMERA_INDEX}")
        return False

    logger.info(f"Camera opened (index={config.CAMERA_INDEX}). Scanning for late students...")
    logger.info(f"School start time: {config.SCHOOL_START_TIME}")
    logger.info(f"Confidence threshold: {config.CONFIDENCE_THRESHOLD}")

    logged_today: set = set()  # student_ids already logged today
    last_reload = time.time()
    last_date = date.today()

    try:
        while True:
            today = date.today()

            # Reset logged set at midnight
            if today != last_date:
                logged_today.clear()
                last_date = today
                logger.info("New day — cleared today's log set")

            # Calendar check
            if not check_school_day(today):
                logger.info("Non-school day — sleeping 60 seconds")
                time.sleep(60)
                continue

            now = datetime.now().time()

            # Only scan after school start time
            if now < config.SCHOOL_START_TIME:
                wait_min = (
                    (config.SCHOOL_START_TIME.hour * 60 + config.SCHOOL_START_TIME.minute)
                    - (now.hour * 60 + now.minute)
                )
                logger.info(f"School hasn't started yet. Waiting {wait_min} minutes.")
                time.sleep(min(wait_min * 60, 300))
                continue

            # Reload face database periodically (picks up newly enrolled students)
            if time.time() - last_reload > RELOAD_INTERVAL_SECONDS:
                logger.info("Reloading face database from API...")
                # Also run enrollment for any students added since last reload
                run_enrollment()
                students = get_all_enrolled_students()
                recognizer.load_students(students)
                last_reload = time.time()

            ret, frame_bgr = cap.read()
            if not ret:
                logger.warning("Failed to read frame from camera")
                time.sleep(1)
                continue

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            student_id, house_id, confidence = recognizer.recognize(frame_rgb)

            if student_id is not None and student_id not in logged_today:
                logger.info(
                    f"Detected student {student_id} (confidence={confidence:.2f}) at {now.strftime('%H:%M:%S')}"
                )
                image_bytes = recognizer.get_face_image_bytes(frame_rgb)
                result = post_late_entry(
                    student_id=student_id,
                    house_id=house_id,
                    arrival_time=now,
                    entry_date=today,
                    confidence=confidence,
                    image_bytes=image_bytes,
                )
                if result and result.get("id"):
                    logged_today.add(student_id)
                    logger.info(f"Logged late entry id={result['id']} for student {student_id}")

            time.sleep(config.SCAN_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        cap.release()
        logger.info("Camera released")
    return True


def main():
    parser = argparse.ArgumentParser(description="Attendify Camera Service")
    parser.add_argument("--enroll-only", action="store_true", help="Run enrollment then exit")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Attendify.ai Camera Service")
    logger.info(f"  API:     {config.API_BASE_URL}")
    logger.info(f"  Photos:  {config.BACKEND_UPLOADS_URL}")
    logger.info("=" * 60)

    # Authenticate with backend API
    if not api_client.login():
        logger.error("Cannot authenticate with backend — check .env credentials")
        sys.exit(1)

    # Always run enrollment on start (idempotent — skips already-enrolled students)
    run_enrollment()

    if args.enroll_only:
        logger.info("Enrollment-only mode — exiting.")
        return

    # Load all enrolled students into memory
    logger.info("Loading enrolled students from API...")
    students = get_all_enrolled_students()
    recognizer = FaceRecognizer(confidence_threshold=config.CONFIDENCE_THRESHOLD)
    recognizer.load_students(students)

    if not recognizer.known_encodings:
        logger.warning(
            "No enrolled students found. "
            "Add students with photos via the web UI, then run enrollment."
        )

    run_camera(recognizer)


if __name__ == "__main__":
    main()
