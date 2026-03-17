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

# Create all DB tables
Base.metadata.create_all(bind=engine)

# Load environment variables for the default API Key
load_dotenv()
DEFAULT_API_KEY = os.getenv("WASENDER_API_KEY", "")

app = FastAPI(title="CBMS Pro API")

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
        # Redirect unauthenticated users to login page
        return RedirectResponse(url="/login")
        
    if exc.status_code == 403:
        # Serve unauthorized page for forbidden access
        return templates.TemplateResponse("unauthorized.html", {"request": request, "user": user}, status_code=403)
        
    return HTMLResponse(status_code=exc.status_code, content=str(exc.detail))

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
    media_url: str = Form(None),
    document_name: str = Form(None),
    latitude: float = Form(None),
    longitude: float = Form(None),
    location_name: str = Form(None),
    location_address: str = Form(None),
    contact_name: str = Form(None),
    contact_phone: str = Form(None),
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

        count = 0
        for _, row in df.iterrows():
            phone = str(row['Phone']).split('.')[0].strip()
            
            # Format text safely
            def format_text(txt):
                if not txt: return ""
                try:
                    return txt.format(**row.to_dict()) if "{" in txt else txt
                except KeyError:
                    return txt

            types = [t.strip() for t in message_type.split(',')]
            for t in types:
                if not t: continue
                payload = {"to": phone}
                
                if t == "text":
                    payload["text"] = format_text(text_message)
                elif t == "image":
                    payload["imageUrl"] = media_url
                    cap = format_text(image_caption)
                    if cap: payload["text"] = cap
                elif t == "video":
                    payload["videoUrl"] = media_url
                    cap = format_text(video_caption)
                    if cap: payload["text"] = cap
                elif t == "document":
                    payload["documentUrl"] = media_url
                    payload["fileName"] = document_name or "Document"
                    cap = format_text(document_caption)
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
                
                SEND_QUEUE.enqueue(payload, final_api_key)
                count += 1

        return {"status": "success", "messages_queued": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)