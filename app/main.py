import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pandas as pd
import io
import uvicorn
from app.queue_manager import SEND_QUEUE
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import HTMLResponse
from app.database import engine, Base
from app.routers import auth, mfa, oauth, users, admin
from app.auth import get_current_user, get_current_active_user_or_401
from starlette.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

# Create all DB tables
Base.metadata.create_all(bind=engine)

# Load environment variables for the default API Key
load_dotenv()
DEFAULT_API_KEY = os.getenv("WASENDER_API_KEY", "")

app = FastAPI(title="CBMS Pro API")

# Add SessionMiddleware (required for OAuth state management)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-secret-key")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Register Authentication and User Routers
app.include_router(auth.router)
app.include_router(mfa.router)
app.include_router(oauth.router)
app.include_router(users.router)
app.include_router(admin.router)

# Custom 404 Handler for UI Request
@app.exception_handler(StarletteHTTPException)
async def custom_exception_handler(request: Request, exc: StarletteHTTPException):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        user = await get_current_user(request, db)
    finally:
        db.close()
        
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request, "user": user}, status_code=404)
    
    if exc.status_code == 401:
        # Only redirect to login page for browser navigation (HTML requests)
        # For API calls or AJAX, return JSON so the frontend can handle it
        if not request.url.path.startswith("/auth/") and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse(url="/login")
        
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": exc.detail})
        
    if exc.status_code == 403:
        # Serve unauthorized page for forbidden access
        return templates.TemplateResponse("unauthorized.html", {"request": request, "user": user}, status_code=403)
        
    # For other errors (like 400 Bad Request), return JSON for AJAX compatibility
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, user = Depends(get_current_user)):
    """Serve the landing page to unauthenticated users."""
    if user:
         # If already logged in, skip the landing and go straight to the dash
         return RedirectResponse(url="/dashboard")
         
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, user = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user = Depends(get_current_active_user_or_401)):
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, user = Depends(get_current_active_user_or_401)):
    """The protected main broadcasting page."""
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.post("/send-campaign")
async def handle_form(
    user = Depends(get_current_active_user_or_401),
    message_type: str = Form(...),
    api_key: str = Form(None),
    text_message: str = Form(None),
    image_caption: str = Form(None),
    video_caption: str = Form(None),
    document_caption: str = Form(None),
    location_caption: str = Form(None),
    image_url: str = Form(None),
    video_url: str = Form(None),
    document_url: str = Form(None),
    document_name: str = Form(None),
    latitude: float = Form(None),
    longitude: float = Form(None),
    location_name: str = Form(None),
    location_address: str = Form(None),
    contact_name: str = Form(None),
    contact_phone: str = Form(None),
    audio_url: str = Form(None),
    audio_text: str = Form(None),
    sticker_url: str = Form(None),
    sticker_text: str = Form(None),
    poll_question: str = Form(None),
    poll_options: str = Form(None),
    poll_multi_select: bool = Form(False),
    excel_file: UploadFile = File(...)
):
    try:
        final_api_key = api_key if api_key and api_key.strip() else DEFAULT_API_KEY
        if not final_api_key:
            return {"error": "No API Key provided. Set WASENDER_API_KEY in .env or provide it in the form."}

        content = await excel_file.read()
        df = pd.read_excel(io.BytesIO(content))

        if 'Phone' not in df.columns:
            return {"error": "Excel must have a 'Phone' column"}
        
        # Filter valid phones first to get accurate count
        def is_valid_phone(p):
            p_str = str(p).split('.')[0].strip().lower()
            return p_str and p_str != 'nan'

        df = df[df['Phone'].apply(is_valid_phone)]
        contacts_reached = len(df)
        count = 0

        for _, row in df.iterrows():
            phone = str(row['Phone']).split('.')[0].strip()
            
            # Format text safely
            def format_text(txt):
                if not txt: return ""
                try:
                    return str(txt).format(**row.to_dict()) if "{" in str(txt) else str(txt)
                except (KeyError, ValueError, TypeError):
                    return str(txt)

            types = [t.strip() for t in message_type.split(',')]
            for t in types:
                if not t: continue
                payload: dict = {"to": phone}
                
                if t == "text":
                    payload["text"] = format_text(text_message)
                elif t == "image":
                    payload["imageUrl"] = image_url
                    cap = format_text(image_caption)
                    if cap: payload["text"] = cap
                elif t == "video":
                    payload["videoUrl"] = video_url
                    cap = format_text(video_caption)
                    if cap: payload["text"] = cap
                elif t == "document":
                    payload["documentUrl"] = document_url
                    payload["fileName"] = document_name or "Document"
                    cap = format_text(document_caption)
                    if cap: payload["text"] = cap
                elif t == "audio":
                    payload["audioUrl"] = audio_url
                    cap = format_text(audio_text)
                    if cap: payload["text"] = cap
                elif t == "sticker":
                    payload["stickerUrl"] = sticker_url
                    cap = format_text(sticker_text)
                    if cap: payload["text"] = cap
                elif t == "location":
                    cap = format_text(location_caption)
                    if cap: payload["text"] = cap
                    payload["location"] = {
                        "latitude": latitude,
                        "longitude": longitude,
                        "name": location_name,
                        "address": location_address
                    }
                elif t == "contact":
                    payload["contact"] = {
                        "name": contact_name,
                        "phone": contact_phone
                    }
                elif t == "poll":
                    options_list = [format_text(opt.strip()) for opt in (poll_options or "").split('\n') if opt.strip()]
                    payload["poll"] = {
                        "question": format_text(poll_question),
                        "options": options_list,
                        "multiSelect": poll_multi_select
                    }
                
                SEND_QUEUE.enqueue(payload, final_api_key)
                count += 1

        return {"status": "success", "messages_queued": count, "contacts_reached": contacts_reached}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)