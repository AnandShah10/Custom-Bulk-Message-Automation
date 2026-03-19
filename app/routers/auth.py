from fastapi import APIRouter, Depends, HTTPException, status, Response, Form, Request
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, SystemLog
from app.auth import verify_password, create_access_token, get_password_hash, get_current_user
import pyotp
import os
from dotenv import load_dotenv
load_dotenv()
base_url = os.getenv("BASE_URL")
router = APIRouter(tags=["Authentication"])

@router.post("/auth/signup")
async def signup(
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
         raise HTTPException(status_code=400, detail="Passwords do not match")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    new_user = User(
        username=username,
        hashed_password=get_password_hash(password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Log Action
    log = SystemLog(user_id=new_user.id, action="SIGNUP", details=f"User {username} registered via email.")
    db.add(log)
    db.commit()
    
    # Auto-login upon signup
    access_token = create_access_token(data={"sub": new_user.username})
    response = Response(content='{"status":"ok", "message":"Signup successful"}', media_type="application/json")
    response.set_cookie(key="session_token", value=access_token, httponly=True, max_age=18000, samesite="lax")
    return response

@router.post("/auth/login")
async def login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    mfa_code: str = Form(None), # Optional, required if MFA enabled
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    # Handle MFA verification if enabled
    if user.mfa_enabled:
        if not mfa_code:
            raise HTTPException(status_code=401, detail="mfa_required") # Trigger MFA UI
        
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(mfa_code):
            raise HTTPException(status_code=401, detail="invalid_mfa")
            
    # Success Login
    log = SystemLog(user_id=user.id, action="LOGIN", details=f"User {username} logged in successfully.")
    db.add(log)
    db.commit()

    access_token = create_access_token(data={"sub": user.username})
    res = Response(content='{"status":"ok", "message":"Login successful"}', media_type="application/json")
    res.set_cookie(key="session_token", value=access_token, httponly=True, max_age=86400*7, samesite="lax") # 7 days
    return res

@router.post("/auth/logout")
async def logout(response: Response, user = Depends(get_current_user), db: Session = Depends(get_db)):
    if user:
        log = SystemLog(user_id=user.id, action="LOGOUT", details="User logged out manually.")
        db.add(log)
        db.commit()
    
    res = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    res.delete_cookie("session_token")
    return res

import secrets
from datetime import datetime, timedelta

@router.get("/password-reset", response_class=Response)
async def get_password_reset_page(request: Request, user = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/dashboard")
    from app.main import templates
    return templates.TemplateResponse("password_reset.html", {"request": request})

@router.post("/password-reset")
async def request_password_reset(
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == email).first()
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        
        # Send real email
        reset_link = f"{base_url}/reset-password/{token}"
        try:
            from app.email_utils import send_password_reset_email
            await send_password_reset_email(email, reset_link)
            details = f"Reset link sent to {email}"
        except Exception as e:
            details = f"Failed to send reset link to {email}: {str(e)}"
            print(f"DEBUG Error sending email: {e}")
        
        log = SystemLog(user_id=user.id, action="PASSWORD_RESET_REQUEST", details=details)
        db.add(log)
        db.commit()
    
    return {"message": "If an account with that email exists, a reset link has been sent."}

@router.get("/reset-password/{token}", response_class=Response)
async def get_reset_password_confirm_page(request: Request, token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.reset_token == token, User.reset_token_expiry > datetime.utcnow()).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    from app.main import templates
    return templates.TemplateResponse("reset_password_confirm.html", {"request": request, "token": token})

@router.post("/reset-password/{token}")
async def reset_password(
    token: str,
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.reset_token == token, User.reset_token_expiry > datetime.utcnow()).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    user.hashed_password = get_password_hash(password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()
    
    log = SystemLog(user_id=user.id, action="PASSWORD_RESET_SUCCESS", details="Password reset successfully.")
    db.add(log)
    db.commit()
    
    return {"status": "ok", "message": "Password reset successfully. You can now login."}
