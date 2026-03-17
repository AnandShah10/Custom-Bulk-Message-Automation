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
        "username": current_user.username,
        "role": current_user.role,
        "mfa_enabled": current_user.mfa_enabled,
        "google_linked": bool(current_user.google_id),
        "microsoft_linked": bool(current_user.microsoft_id)
    }

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
