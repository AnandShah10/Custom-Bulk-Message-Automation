from fastapi import APIRouter, Depends, HTTPException, status, Response, Form, Request
from fastapi.responses import JSONResponse
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, SystemLog, UserPasskey
from app.auth import verify_password, create_access_token, get_password_hash, get_current_user
import pyotp
import os
import json
import base64
import webauthn
from webauthn import options_to_json, verify_authentication_response, generate_authentication_options
from webauthn.helpers.structs import UserVerificationRequirement, PublicKeyCredentialDescriptor
from dotenv import load_dotenv

load_dotenv()
base_url = os.getenv("BASE_URL")
router = APIRouter(tags=["Authentication"])

# Configuration for WebAuthn (Matches mfa.py)
RP_ID = "localhost" 
ORIGIN = f"http://{RP_ID}:8001"

@router.post("/auth/signup")
async def signup(
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    full_name: str = Form(None),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
         raise HTTPException(status_code=400, detail="Passwords do not match")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    new_user = User(
        username=username,
        full_name=full_name,
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
            # Check for passkeys to include in available methods
            passkeys = db.query(UserPasskey).filter(UserPasskey.user_id == user.id).all()
            available_methods = ["app", "email"]
            if passkeys:
                available_methods.append("passkey")
                
            # If email OTP, send it immediately
            if user.mfa_type == "email":
                # Generate and send code
                from app.email_utils import send_mfa_code_email
                totp = pyotp.TOTP(user.mfa_secret)
                code = totp.now()
                try:
                    await send_mfa_code_email(user.username, code)
                except Exception as e:
                    print(f"Failed to send MFA email: {e}")

            return JSONResponse(
                status_code=401,
                content={
                    "status": "mfa_required",
                    "mfa_type": user.mfa_type,
                    "available_methods": available_methods
                }
            )
        
        # Verify code for both app and email (it's the same TOTP secret)
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(mfa_code, valid_window=1):
            raise HTTPException(status_code=401, detail="invalid_mfa")
            
    # Success Login
    log = SystemLog(user_id=user.id, action="LOGIN", details=f"User {username} logged in successfully.")
    db.add(log)
    db.commit()

    access_token = create_access_token(data={"sub": user.username})
    res = Response(content='{"status":"ok", "message":"Login successful"}', media_type="application/json")
    res.set_cookie(key="session_token", value=access_token, httponly=True, max_age=86400*7, samesite="lax") # 7 days
    return res

@router.post("/auth/resend-mfa")
async def resend_mfa_email(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Resends the MFA code if the type is email."""
    user = db.query(User).filter(User.username == username).first()
    from app.auth import verify_password
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Authentication failed")
    
    if user.mfa_enabled and user.mfa_type == "email":
        totp = pyotp.TOTP(user.mfa_secret)
        code = totp.now()
        from app.email_utils import send_mfa_code_email
        await send_mfa_code_email(user.username, code)
        return {"message": "MFA code resent to your email."}
    
    raise HTTPException(status_code=400, detail="MFA not set to email or not enabled.")

    raise HTTPException(status_code=400, detail="MFA not set to email or not enabled.")

@router.get("/auth/passkey/login/options")
async def get_passkey_login_options(
    request: Request,
    username: str,
    db: Session = Depends(get_db)
):
    """Generates authentication options for Passkey login."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    passkeys = db.query(UserPasskey).filter(UserPasskey.user_id == user.id).all()
    if not passkeys:
        raise HTTPException(status_code=400, detail="No passkeys registered for this user.")
        
    options = webauthn.generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64.b64decode(p.credential_id)) 
            for p in passkeys
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    
    # Store challenge in session as base64 string
    request.session["authentication_challenge"] = base64.b64encode(options.challenge).decode('utf-8')
    request.session["authentication_username"] = username
    
    return json.loads(options_to_json(options))

@router.post("/auth/passkey/login/verify")
async def verify_passkey_login(
    request: Request,
    verification_data: dict,
    db: Session = Depends(get_db)
):
    """Verifies the Passkey response and logs the user in."""
    challenge_b64 = request.session.pop("authentication_challenge", None)
    username = request.session.pop("authentication_username", None)
    
    if not challenge_b64 or not username:
        raise HTTPException(status_code=400, detail="Authentication challenge missing or expired.")
        
    challenge = base64.b64decode(challenge_b64)
        
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    # Standardize the credential ID from base64url (browser) to base64 (DB)
    raw_id_b64url = verification_data.get("id")
    # Convert base64url to standard base64 if needed, though they might match if no special chars
    # Safer to convert:
    temp_id = raw_id_b64url.replace('-', '+').replace('_', '/')
    while len(temp_id) % 4: temp_id += '='
    standard_b64_id = temp_id

    passkey = db.query(UserPasskey).filter(UserPasskey.credential_id == standard_b64_id, UserPasskey.user_id == user.id).first()
    if not passkey:
        raise HTTPException(status_code=400, detail="Passkey not recognized.")
        
    try:
        authentication_verification = verify_authentication_response(
            credential=verification_data,
            expected_challenge=challenge,
            expected_origin=ORIGIN,
            expected_rp_id=RP_ID,
            credential_public_key=base64.b64decode(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
        )
        
        # Update sign count
        passkey.sign_count = authentication_verification.new_sign_count
        
        # Success Login
        log = SystemLog(user_id=user.id, action="LOGIN_PASSKEY", details=f"User {username} logged in via Passkey.")
        db.add(log)
        db.commit()

        access_token = create_access_token(data={"sub": user.username})
        res = Response(content='{"status":"ok", "message":"Login successful"}', media_type="application/json")
        res.set_cookie(key="session_token", value=access_token, httponly=True, max_age=86400*7, samesite="lax")
        return res
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")

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
