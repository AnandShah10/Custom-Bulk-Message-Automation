import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from app.database import get_db
from app.models import User, SystemLog
from app.auth import create_access_token
from dotenv import load_dotenv

load_dotenv()
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["OAuth"])

# Authlib configuration
config_data = {
    'GOOGLE_CLIENT_ID': os.environ.get('GOOGLE_CLIENT_ID', ''),
    'GOOGLE_CLIENT_SECRET': os.environ.get('GOOGLE_CLIENT_SECRET', ''),
    'MICROSOFT_CLIENT_ID': os.environ.get('MICROSOFT_CLIENT_ID', ''),
    'MICROSOFT_CLIENT_SECRET': os.environ.get('MICROSOFT_CLIENT_SECRET', '')
}
starlette_config = Config(environ=config_data)
oauth = OAuth(starlette_config)

# Google OAuth Setup
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Microsoft OAuth Setup (Azure AD v2.0 endpoint)
oauth.register(
    name='microsoft',
    server_metadata_url='https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

@router.get("/auth/login/google")
async def login_google(request: Request):
    """Redirects the user to Google's consent screen."""
    # Try to use BASE_URL for consistency, fallback to request URL
    base_url = os.getenv("BASE_URL")
    if base_url:
        redirect_uri = f"{base_url.rstrip('/')}/auth/google/callback"
    else:
        redirect_uri = request.url_for('auth_google_callback')
        
    logger.info(f"Initiating Google OAuth redirect to: {redirect_uri}")
    logger.info(f"Session content BEFORE redirect: {list(request.session.keys())}")
    return await oauth.google.authorize_redirect(request, redirect_uri, prompt='select_account')

@router.get("/auth/google/callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    """Handles the response from Google after consent."""
    logger.info(f"Callback received. Session keys: {list(request.session.keys())}")
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            raise HTTPException(status_code=400, detail="Could not parse Google user info")
            
        email = user_info.get('email')
        google_id = user_info.get('sub')
        full_name = user_info.get('name')
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Google authentication failed: {str(e)}")

    # Check if user exists by google_id
    user = db.query(User).filter(User.google_id == google_id).first()
    
    # If not found by ID, maybe they signed up with email first? Link them.
    if not user:
        user = db.query(User).filter(User.username == email).first()
        if user:
            user.google_id = google_id
            if not user.full_name:
                user.full_name = full_name
        else:
            # Create a brand new user
            user = User(username=email, google_id=google_id, full_name=full_name, hashed_password="OAUTH_USER_NO_PASSWORD")
            db.add(user)
        
        db.commit()
        db.refresh(user)
        log = SystemLog(user_id=user.id, action="OAUTH_SIGNUP_GOOGLE", details="User registered via Google.")
        db.add(log)

    if not user.is_active:
         raise HTTPException(status_code=400, detail="Account disabled.")

    log = SystemLog(user_id=user.id, action="LOGIN_GOOGLE", details="User logged in via Google.")
    db.add(log)
    db.commit()

    # Issue JWT Token and set cookie
    access_token = create_access_token(data={"sub": user.username})
    response = Response(status_code=302, headers={"Location": "/dashboard"})
    response.set_cookie(key="session_token", value=access_token, httponly=True, max_age=86400*7, samesite="lax")
    return response


@router.get("/auth/login/microsoft")
async def login_microsoft(request: Request):
    """Redirects the user to Microsoft's consent screen."""
    base_url = os.getenv("BASE_URL")
    if base_url:
        redirect_uri = f"{base_url.rstrip('/')}/auth/microsoft/callback"
    else:
        redirect_uri = request.url_for('auth_microsoft_callback')
        
    logger.info(f"Initiating Microsoft OAuth redirect to: {redirect_uri}")
    return await oauth.microsoft.authorize_redirect(request, redirect_uri, prompt='select_account')

@router.get("/auth/microsoft/callback")
async def auth_microsoft_callback(request: Request, db: Session = Depends(get_db)):
    """Handles the response from Microsoft after consent."""
    try:
        token = await oauth.microsoft.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            raise HTTPException(status_code=400, detail="Could not parse Microsoft user info")
            
        email = user_info.get('email') or user_info.get('preferred_username')
        microsoft_id = user_info.get('oid') or user_info.get('sub')
        full_name = user_info.get('name')
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Microsoft authentication failed: {str(e)}")

    user = db.query(User).filter(User.microsoft_id == microsoft_id).first()
    
    if not user:
        user = db.query(User).filter(User.username == email).first()
        if user:
            user.microsoft_id = microsoft_id
            if not user.full_name:
                user.full_name = full_name
        else:
            user = User(username=email, microsoft_id=microsoft_id, full_name=full_name, hashed_password="OAUTH_USER_NO_PASSWORD")
            db.add(user)
            
        db.commit()
        db.refresh(user)
        log = SystemLog(user_id=user.id, action="OAUTH_SIGNUP_MICROSOFT", details="User registered via Microsoft.")
        db.add(log)

    if not user.is_active:
         raise HTTPException(status_code=400, detail="Account disabled.")

    log = SystemLog(user_id=user.id, action="LOGIN_MICROSOFT", details="User logged in via Microsoft.")
    db.add(log)
    db.commit()

    access_token = create_access_token(data={"sub": user.username})
    response = Response(status_code=302, headers={"Location": "/dashboard"})
    response.set_cookie(key="session_token", value=access_token, httponly=True, max_age=86400*7, samesite="lax")
    return response
