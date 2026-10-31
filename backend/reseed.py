cat > ~/Desktop/attendify/backend/reseed.py << 'EOF'
""" Force re-seed: delete and recreate all users with a fresh password hashes."""
from database import SessionLocal
import models
from services.auth_service import hash_password

db = SessionLocal()

users_to_create = [
    {"name": "Admin", "email": "admin@attendify.ai", "password": "admin123", "role": "admin"},
    {"name": "Demo Teacher", "email": "teacher@attendify.ai", "password": "teacher123", "role": "teacher"},
]

for u in users_to_create:
    existing = db.query(models.User).filter(models.User.email == u["email"]).first()
    if existing:
        db.delete(existing)
        db.commit()
        print(f"  Deleted: {u['email']}")
    user = models.User(
        name=u["name"],
        email=u["email"],
        password_hash=hash_password(u["password"]),
        role=u["role"],
    )
    db.add(user)
    print(f"  Created {u['role']}: {u['email']}")

db.commit()
db.close()
print("Reseed complete.")
EOF
