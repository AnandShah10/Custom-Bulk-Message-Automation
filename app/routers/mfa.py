from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, SystemLog
from app.auth import get_current_active_user_or_401
import pyotp
import qrcode
import io
import base64

from starlette.requests import Request
import webauthn
from webauthn import options_to_json, verify_registration_response, generate_registration_options
from webauthn.helpers.structs import AuthenticatorSelectionCriteria, AuthenticatorAttachment, UserVerificationRequirement, AttestationConveyancePreference
import json

router = APIRouter(tags=["MFA"])

# Configuration for WebAuthn
RP_ID = "localhost" # Should be domain in production
RP_NAME = "CBMS Pro"
ORIGIN = f"http://{RP_ID}:8001" # Port matches user's running port

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

@router.post("/mfa/type")
async def update_mfa_type(
    mfa_type: str = Form(...),
    user: User = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    """Changes the active MFA type (app, email, or passkey)."""
    if mfa_type not in ["app", "email", "passkey"]:
        raise HTTPException(status_code=400, detail="Invalid MFA type.")
    
    if mfa_type == "passkey":
        # Check if user has at least one passkey
        from app.models import UserPasskey
        passkey = db.query(UserPasskey).filter(UserPasskey.user_id == user.id).first()
        if not passkey:
            raise HTTPException(status_code=400, detail="Please register a Passkey first.")

    user.mfa_type = mfa_type
    user.mfa_enabled = True # Always enable if a specific type is being selected
    
    log = SystemLog(user_id=user.id, action="MFA_TYPE_CHANGED", details=f"User switched MFA type to {mfa_type} and ensured MFA is enabled.")
    db.add(log)
    db.commit()
    return {"message": f"MFA method switched to {mfa_type} successfully."}

@router.get("/mfa/passkey/register/options")
async def get_passkey_register_options(
    request: Request,
    user: User = Depends(get_current_active_user_or_401)
):
    """Generates options for Passkey registration."""
    options = webauthn.generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(user.id).encode('utf-8'),
        user_name=user.username,
        user_display_name=user.full_name or user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM, # Require platform authenticators (FaceID, TouchID, Windows Hello)
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    
    # Store challenge in session as base64 string
    import base64
    request.session["registration_challenge"] = base64.b64encode(options.challenge).decode('utf-8')
    
    return json.loads(options_to_json(options))

@router.post("/mfa/passkey/register/verify")
async def verify_passkey_registration(
    request: Request,
    verification_data: dict, # JSON body
    user: User = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    """Verifies Passkey registration and stores the credential."""
    challenge_b64 = request.session.pop("registration_challenge", None)
    if not challenge_b64:
        raise HTTPException(status_code=400, detail="Registration challenge missing or expired.")
    
    import base64
    challenge = base64.b64decode(challenge_b64)

    try:
        registration_verification = verify_registration_response(
            credential=verification_data,
            expected_challenge=challenge,
            expected_origin=ORIGIN,
            expected_rp_id=RP_ID,
        )
        
        from app.models import UserPasskey
        import base64
        
        # Store the passkey using standard base64 for database safety
        new_passkey = UserPasskey(
            user_id=user.id,
            credential_id=base64.b64encode(registration_verification.credential_id).decode('utf-8'),
            public_key=base64.b64encode(registration_verification.credential_public_key).decode('utf-8'),
            sign_count=registration_verification.sign_count
        )
        db.add(new_passkey)
        
        # Ensure a fallback secret exists for compatibility if they ever switch to TOTP
        if not user.mfa_secret:
            import pyotp
            user.mfa_secret = pyotp.random_base32()

        db.commit()
        return {"status": "ok", "message": "Passkey registered successfully! You can now select it as your MFA method above."}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")

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
