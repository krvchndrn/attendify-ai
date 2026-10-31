from datetime import datetime, date as dt_date, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
import models
from services.auth_service import verify_password, hash_password, create_access_token, get_current_user, require_admin
from services.activity_log_service import log_activity

router = APIRouter(prefix="/auth", tags=["Auth"])

VALID_ROLES = ("admin", "teacher", "house_manager")


def _user_to_dict(user: models.User, house_name: str = None) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "assigned_house_id": user.assigned_house_id,
        "assigned_house_name": house_name,
        "assigned_class": user.assigned_class,
    }


def _house_name_for(db: Session, house_id: Optional[int]) -> Optional[str]:
    if not house_id:
        return None
    house = db.query(models.House).filter(models.House.id == house_id).first()
    return house.name if house else None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
  user = db.query(models.User).filter(models.User.email == form_data.username).first()
    print(f"DEBUG LOGIN: email={form_data.username!r} user_found={user is not None}")
    if user:
        import hashlib
        computed = hashlib.sha256(form_data.password.encode()).hexdigest()
        print(f"DEBUG LOGIN: computed={computed[:12]}... stored={user.password_hash[:12]}... match={computed == user.password_hash}")
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user.last_login_at = datetime.utcnow()
    db.commit()
    log_activity(db, user.id, "logged_in", f"{user.name} logged in")

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_to_dict(user, _house_name_for(db, user.assigned_house_id)),
    }


@router.post("/logout")
def logout(current_user: models.User = Depends(get_current_user)):
    # JWT is stateless; client drops the token
    return {"message": "Logged out successfully"}


@router.get("/me")
def me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_to_dict(current_user, _house_name_for(db, current_user.assigned_house_id))


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    rows = (
        db.query(models.User, models.House.name.label("house_name"))
        .join(models.House, models.User.assigned_house_id == models.House.id, isouter=True)
        .order_by(models.User.created_at)
        .all()
    )
    return [
        {
            **_user_to_dict(u, house_name),
            "created_at": u.created_at,
            "last_login_at": u.last_login_at,
        }
        for u, house_name in rows
    ]


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "teacher"
    assigned_house_id: Optional[int] = None
    assigned_class: Optional[str] = None


@router.post("/register")
def register_user(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {VALID_ROLES}")

    assigned_house_id = None
    if payload.role == "house_manager":
        if not payload.assigned_house_id:
            raise HTTPException(status_code=400, detail="assigned_house_id is required for house_manager role")
        house = db.query(models.House).filter(models.House.id == payload.assigned_house_id).first()
        if not house:
            raise HTTPException(status_code=404, detail="House not found")
        existing_manager = (
            db.query(models.User)
            .filter(models.User.role == "house_manager", models.User.assigned_house_id == payload.assigned_house_id)
            .first()
        )
        if existing_manager:
            raise HTTPException(status_code=400, detail=f"{house.name} already has a house manager assigned")
        assigned_house_id = payload.assigned_house_id

    assigned_class = payload.assigned_class if payload.role == "teacher" else None

    user = models.User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        assigned_house_id=assigned_house_id,
        assigned_class=assigned_class,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_activity(db, current_user.id, f"added_{payload.role}", f"{current_user.name} added {payload.role} {user.name} ({user.email})")

    return _user_to_dict(user, _house_name_for(db, user.assigned_house_id))


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    deleted_name, deleted_email, deleted_role = user.name, user.email, user.role
    db.delete(user)
    db.commit()

    log_activity(db, current_user.id, f"deleted_{deleted_role}", f"{current_user.name} removed {deleted_role} {deleted_name} ({deleted_email})")

    return {"message": "User deleted"}


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.put("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not payload.new_password or len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user.password_hash = hash_password(payload.new_password)
    db.commit()

    log_activity(db, current_user.id, "reset_password", f"{current_user.name} reset the password for {user.name}")

    return {"message": "Password reset"}


@router.get("/activity-log")
def activity_log(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    date_from: Optional[dt_date] = None,
    date_to: Optional[dt_date] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    query = db.query(models.ActivityLog, models.User.name.label("user_name")).join(
        models.User, models.ActivityLog.user_id == models.User.id, isouter=True
    )
    if user_id:
        query = query.filter(models.ActivityLog.user_id == user_id)
    if action:
        query = query.filter(models.ActivityLog.action == action)
    if date_from:
        query = query.filter(models.ActivityLog.created_at >= date_from)
    if date_to:
        query = query.filter(models.ActivityLog.created_at < date_to + timedelta(days=1))

    total = query.count()
    rows = (
        query.order_by(models.ActivityLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        {
            "id": entry.id,
            "user_id": entry.user_id,
            "user_name": user_name or "System",
            "action": entry.action,
            "details": entry.details,
            "created_at": entry.created_at,
        }
        for entry, user_name in rows
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}
