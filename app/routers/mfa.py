from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, SystemLog
from app.auth import get_current_active_user_or_401
import pyotp
import qrcode
import io
import base64

router = APIRouter(tags=["MFA"])

@router.get("/mfa/setup")
async def setup_mfa(user: User = Depends(get_current_active_user_or_401), db: Session = Depends(get_db)):
    """Generates a new MFA secret and returns the QR code as a base64 image."""
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is already enabled.")

    # Generate a new random secret if not present
    if not user.mfa_secret:
        user.mfa_secret = pyotp.random_base32()
        db.commit()

    # Generate provisioning URI
    totp = pyotp.TOTP(user.mfa_secret)
    provisioning_uri = totp.provisioning_uri(name=user.username, issuer_name="CBMS Pro")

    # Generate QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert image to base64 string for easy display in HTML
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    return {"qr_code_base64": img_str, "secret": user.mfa_secret}

@router.post("/mfa/enable")
async def enable_mfa(
    mfa_code: str = Form(...),
    user: User = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    """Verifies the code and officially enables MFA for the user."""
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA already enabled")
        
    if not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA setup not initiated.")

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(mfa_code):
        raise HTTPException(status_code=400, detail="Invalid MFA code. Try again.")

    user.mfa_enabled = True
    log = SystemLog(user_id=user.id, action="MFA_ENABLED", details="User enabled Two-Factor Authentication.")
    db.add(log)
    db.commit()

    return {"status": "ok", "message": "MFA enabled successfully."}

@router.post("/mfa/disable")
async def disable_mfa(
    password: str = Form(...),
    user: User = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    """Disables MFA, requires password verification."""
    from app.auth import verify_password
    
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    user.mfa_enabled = False
    
    log = SystemLog(user_id=user.id, action="MFA_DISABLED", details="User disabled Two-Factor Authentication.")
    db.add(log)
    db.commit()

    return {"status": "ok", "message": "MFA disabled successfully."}
