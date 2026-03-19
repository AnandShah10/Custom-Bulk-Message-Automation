from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, SystemLog
from app.auth import get_current_active_user_or_401, verify_password, get_password_hash

router = APIRouter(tags=["Users Profile"])

@router.get("/users/me")
async def read_users_me(current_user: User = Depends(get_current_active_user_or_401)):
    """Returns the current logged-in user's profile data."""
    return {
        "id": current_user.id,
        "public_id": current_user.public_id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "mfa_enabled": current_user.mfa_enabled,
        "google_linked": bool(current_user.google_id),
        "microsoft_linked": bool(current_user.microsoft_id)
    }

@router.post("/users/me/profile")
async def update_profile(
    full_name: str = Form(None),
    current_user: User = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    """Update user's profile details."""
    if full_name is not None:
        current_user.full_name = full_name
        
    db.commit()
    return {"status": "ok", "message": "Profile updated successfully.", "full_name": current_user.full_name}

@router.post("/users/me/password")
async def update_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    current_user: User = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    """Allows users to reset their own password."""
    # Accounts created purely via OAuth won't have a valid password to check
    if current_user.hashed_password == "OAUTH_USER_NO_PASSWORD":
         raise HTTPException(status_code=400, detail="OAuth accounts cannot change passwords this way.")

    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
        
    current_user.hashed_password = get_password_hash(new_password)
    
    log = SystemLog(user_id=current_user.id, action="PASSWORD_CHANGE", details="User changed their password.")
    db.add(log)
    db.commit()
    
    return {"status": "ok", "message": "Password updated successfully."}

@router.get("/users/me/logs")
async def get_my_logs(current_user: User = Depends(get_current_active_user_or_401), db: Session = Depends(get_db)):
    """Returns the last 10 logs for the current user."""
    logs = db.query(SystemLog).filter(SystemLog.user_id == current_user.id).order_by(SystemLog.created_at.desc()).limit(10).all()
    return [{"timestamp": l.created_at, "action": l.action, "details": l.details} for l in logs]
