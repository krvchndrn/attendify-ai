from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from database import engine, run_migrations
import models
import os

models.Base.metadata.create_all(bind=engine)
run_migrations(engine)


def seed_initial_data():
    """Idempotent seed: create default houses and admin user if they don't exist."""
    from database import SessionLocal
    from services.auth_service import hash_password
    db = SessionLocal()
    try:
        # Seed houses only if none exist
        if db.query(models.House).count() == 0:
            default_houses = [
                {"name": "Red House",    "colour": "#ef4444", "current_points": 1000},
                {"name": "Blue House",   "colour": "#3b82f6", "current_points": 1000},
                {"name": "Green House",  "colour": "#22c55e", "current_points": 1000},
                {"name": "Yellow House", "colour": "#eab308", "current_points": 1000},
            ]
            for h in default_houses:
                db.add(models.House(**h))
            db.commit()
            print("Seeded 4 default houses.")

        # Seed admin user only if no admin exists
        if not db.query(models.User).filter(models.User.role == "admin").first():
            db.add(models.User(
                name="Admin",
                email="admin@attendify.ai",
                password_hash=hash_password("admin123"),
                role="admin",
            ))
            db.commit()
            print("Seeded default admin user.")
    finally:
        db.close()


seed_initial_data()

from routers import auth, houses, students, late_entries, analytics, calendar, recognition, house_manager, chat
from services.scheduler_service import generate_weekly_reports_job

app = FastAPI(title="Attendify.ai API", version="1.0.0")

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://0.0.0.0:3000",
    "https://frontend-production-8713d.up.railway.app",
]
# Allow any extra origins set via env var (comma-separated)
_extra = os.environ.get("CORS_ORIGINS", "")
if _extra:
    ALLOWED_ORIGINS += [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"
app.include_router(auth.router, prefix=PREFIX)
app.include_router(houses.router, prefix=PREFIX)
app.include_router(students.router, prefix=PREFIX)
app.include_router(late_entries.router, prefix=PREFIX)
app.include_router(analytics.router, prefix=PREFIX)
app.include_router(calendar.router, prefix=PREFIX)
app.include_router(recognition.router, prefix=PREFIX)
app.include_router(house_manager.router, prefix=PREFIX)
app.include_router(chat.router, prefix=PREFIX)

scheduler = BackgroundScheduler()
scheduler.add_job(generate_weekly_reports_job, "cron", day_of_week="mon", hour=6, minute=0)
scheduler.start()

# Serve uploaded files (captured images, student photos)
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/")
def root():
    return {"message": "Attendify.ai Backend is running"}


@app.get("/health")
def health():
    return {"status": "ok"}
