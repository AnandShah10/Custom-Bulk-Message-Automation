import sys
import os

# Add the parent directory to sys.path so we can import 'app'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models import User
from app.auth import get_password_hash

# Ensure tables exist
Base.metadata.create_all(bind=engine)

def create_admin():
    db = SessionLocal()
    admin_email = "admin@cbmspro.com"
    admin_pass = "Admin123!"
    
    existing_admin = db.query(User).filter(User.username == admin_email).first()
    if existing_admin:
        print("Admin user already exists.")
        db.close()
        return

    admin_user = User(
        username=admin_email,
        hashed_password=get_password_hash(admin_pass),
        role="admin",
        is_active=True
    )
    
    db.add(admin_user)
    db.commit()
    db.close()
    print(f"Admin user created defined as '{admin_email}' with password '{admin_pass}'.")

if __name__ == "__main__":
    create_admin()
