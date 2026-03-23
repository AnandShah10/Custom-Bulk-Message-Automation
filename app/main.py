import os
import logging
from logging.handlers import RotatingFileHandler
import datetime as dt
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
from app.routers import auth, mfa, oauth, users, admin, sessions, support, leads, campaigns, analytics
from app.models import User, Lead, Campaign, CampaignLog, CreditTransaction, SystemLog
from app.auth import get_current_user, get_current_active_user_or_401
from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal, get_db
from starlette.responses import RedirectResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.reporting import generate_campaign_pdf

CREDIT_COSTS = {
    "text": 1,
    "image": 2,
    "video": 5,
    "document": 3,
    "audio": 2,
    "location": 2,
    "contact": 1,
    "sticker": 1,
    "poll": 5
}

# Create all DB tables
Base.metadata.create_all(bind=engine)

# Configure Logging
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = 'app.log'

# File Handler with UTF-8 support
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# Stream Handler (Console) - Using a wrapper or just hoping for the best on modern terminals
import sys
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(logging.INFO)

# Root Logger Config
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler]
)

logger = logging.getLogger(__name__)

# Load environment variables for the default API Key
load_dotenv()
DEFAULT_API_KEY = os.getenv("WASENDER_API_KEY", "")

app = FastAPI(title="CBMS Pro API")

# Add SessionMiddleware (required for OAuth state management)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-secret-key")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)

# Add ProxyHeadersMiddleware to handle ngrok/proxies correctly
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Register Authentication and User Routers
app.include_router(auth.router)
app.include_router(mfa.router)
app.include_router(oauth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(sessions.router)
app.include_router(support.router)
app.include_router(leads.router)
app.include_router(campaigns.router)
app.include_router(analytics.router)

@app.on_event("startup")
async def on_startup():
    # Ensure database columns exist for new features
    # This is a simple migration handle for SQLite without Alembic
    from sqlalchemy import text
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        # Check if columns exist
        result = db.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        if "whatsapp_session_id" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN whatsapp_session_id VARCHAR"))
            print("Added whatsapp_session_id column")
        if "whatsapp_session_status" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN whatsapp_session_status VARCHAR DEFAULT 'disconnected'"))
            print("Added whatsapp_session_status column")
        
        if "public_id" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN public_id VARCHAR(36)"))
            print("Added public_id column")
            
        if "full_name" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR"))
            print("Added full_name column")

        if "mfa_type" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN mfa_type VARCHAR DEFAULT 'app'"))
            print("Added mfa_type column")

        if "credits" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN credits INTEGER DEFAULT 0"))
            print("Added credits column")

        # Check campaigns table
        result = db.execute(text("PRAGMA table_info(campaigns)"))
        columns = [row[1] for row in result]
        if "category" not in columns:
            db.execute(text("ALTER TABLE campaigns ADD COLUMN category VARCHAR DEFAULT 'General'"))
            print("Added category column to campaigns")

        # Create new tables if they don't exist
        # Base.metadata.create_all is already called at the top, 
        # but for existing DBs we need to ensure they are created.
        Base.metadata.create_all(bind=engine)
        print("Ensured all marketing tables exist")

        db.commit()

        # Set default credits for admin if they have 0
        db.execute(text("UPDATE users SET credits = 1000 WHERE role = 'admin' AND (credits = 0 OR credits IS NULL)"))
        db.commit()

        # Backfill UUIDs for existing users who don't have one
        import uuid
        users_without_uuid = db.execute(text("SELECT id FROM users WHERE public_id IS NULL")).fetchall()
        for user_row in users_without_uuid:
            new_uuid = str(uuid.uuid4())
            db.execute(text("UPDATE users SET public_id = :uuid WHERE id = :id"), {"uuid": new_uuid, "id": user_row[0]})
            print(f"Backfilled UUID {new_uuid} for user ID {user_row[0]}")
        
        if users_without_uuid:
            db.commit()
            print(f"Backfilled {len(users_without_uuid)} users with UUIDs")
    except Exception as e:
        print(f"Startup migration failed: {e}")
    finally:
        db.close()

@app.get("/migrate")
async def manual_migrate():
    from sqlalchemy import text
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        result = db.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        msg = f"Columns before: {columns}. "
        if "whatsapp_session_id" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN whatsapp_session_id VARCHAR"))
            msg += "Added whatsapp_session_id. "
        if "whatsapp_session_status" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN whatsapp_session_status VARCHAR DEFAULT 'disconnected'"))
            msg += "Added whatsapp_session_status. "
        
        # Campaigns table
        result = db.execute(text("PRAGMA table_info(campaigns)"))
        camp_cols = [row[1] for row in result]
        if "category" not in camp_cols:
            db.execute(text("ALTER TABLE campaigns ADD COLUMN category VARCHAR DEFAULT 'General'"))
            msg += "Added campaigns.category. "
        db.commit()
        return {"status": "success", "message": msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
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

@app.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request, user = Depends(get_current_active_user_or_401)):
    """The WhatsApp session management page."""
    return templates.TemplateResponse("sessions.html", {"request": request, "user": user})

@app.get("/leads", response_class=HTMLResponse)
async def leads_page(request: Request, user = Depends(get_current_active_user_or_401)):
    """The Lead management page."""
    return templates.TemplateResponse("leads.html", {"request": request, "user": user})

@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, user = Depends(get_current_active_user_or_401)):
    """The Campaign History and Analytics page."""
    return templates.TemplateResponse("history.html", {"request": request, "user": user})

@app.get("/payments", response_class=HTMLResponse)
async def payments_page(request: Request, user = Depends(get_current_active_user_or_401)):
    """The Payment and Credit History page."""
    return templates.TemplateResponse("payments.html", {"request": request, "user": user})

@app.get("/campaigns/{campaign_id}/report/pdf")
async def download_campaign_report(
    campaign_id: int, 
    user = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    """Generates and downloads a PDF report for a campaign."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == user.id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    logs = db.query(CampaignLog).filter(CampaignLog.campaign_id == campaign.id).all()
    
    pdf_content = generate_campaign_pdf(campaign, logs)
    
    # Handle both fpdf (str) and fpdf2 (bytes/bytearray)
    if isinstance(pdf_content, str):
        pdf_content = pdf_content.encode('latin-1')
    
    headers = {
        'Content-Disposition': f'attachment; filename="Campaign_Report_{campaign.id}.pdf"'
    }
    return StreamingResponse(io.BytesIO(pdf_content), media_type="application/pdf", headers=headers)

@app.post("/campaigns/credits/topup")
async def topup_credits(
    request: Request,
    user = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    """Mock endpoint for adding credits via the UI."""
    data = await request.json()
    amount = data.get("amount", 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    
    user.credits += amount
    transaction = CreditTransaction(
        user_id=user.id,
        amount=amount,
        type="purchase",
        description=f"Top-up: {amount} Credits (Mock)"
    )
    db.add(transaction)
    db.commit()
    return {"status": "success", "new_balance": user.credits}

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
    excel_file: UploadFile = File(None), # Optional if using saved leads
    source_type: str = Form("excel"),
    lead_category: str = Form("all"),
    campaign_category: str = Form("General"),
    db: Session = Depends(get_db)
):
    try:
        # Re-fetch user from the current db session to ensure credit updates persist
        user = db.query(User).filter(User.id == user.id).first()
        
        # Priority: Form API Key > User's Session API Key > Master/Default API Key
        final_api_key = api_key.strip() if api_key and api_key.strip() else None
        
        if not final_api_key:
            if user.whatsapp_session_id and user.whatsapp_session_status == "connected" and user.custom_api_key:
                final_api_key = user.custom_api_key
                logging.info(f"Using user-specific session API key for {user.username}")
            else:
                final_api_key = DEFAULT_API_KEY
                logging.info(f"Using default system API key for {user.username}")
            
        if not final_api_key:
            return {"error": "No API Key provided. Set WASENDER_API_KEY in .env or provide it in the form."}

        if not final_api_key:
            return {"error": "No API Key provided. Set WASENDER_API_KEY in .env or provide it in the form."}

        # Source Recipients
        recipients = []
        if source_type == "excel":
            if not excel_file:
                return {"error": "Excel file is required for Direct Upload source."}
            content = await excel_file.read()
            df = pd.read_excel(io.BytesIO(content))
            if 'Phone' not in df.columns:
                return {"error": "Excel must have a 'Phone' column"}
            
            # Filter valid phones
            def is_valid_phone(p):
                p_str = str(p).split('.')[0].strip().lower()
                return p_str and p_str != 'nan'
            
            df = df[df['Phone'].apply(is_valid_phone)]
            for _, row in df.iterrows():
                phone = str(row['Phone']).split('.')[0].strip()
                # Include all row data for formatting
                recipients.append({"phone": phone, "metadata": row.to_dict()})
        else:
            # Saved Leads
            query = db.query(Lead).filter(Lead.user_id == user.id)
            if lead_category != "all":
                query = query.filter(Lead.category == lead_category)
            
            db_leads = query.all()
            for l in db_leads:
                meta = json.loads(l.metadata_json) if l.metadata_json else {}
                meta.update({"Phone": l.phone, "Name": l.name or ""})
                recipients.append({"phone": l.phone, "metadata": meta})

        contacts_reached = len(recipients)
        if contacts_reached == 0:
            return {"error": "No valid recipients found."}
        
        types = [t.strip() for t in message_type.split(',')]
        
        # Dynamic Credit Calculation
        total_cost_per_contact = sum(CREDIT_COSTS.get(t, 1) for t in types if t)
        total_cost = contacts_reached * total_cost_per_contact

        # Credit Check
        if user.role != "admin" and user.credits < total_cost:
            return {"error": f"Insufficient credits. Required: {total_cost}, Available: {user.credits}"}

        # Initialize Campaign
        campaign_name = f"Campaign {excel_file.filename}" if source_type == "excel" else f"Campaign: {lead_category} ({dt.datetime.now().strftime('%Y-%m-%d %H:%M')})"
        campaign = Campaign(
            user_id=user.id,
            name=campaign_name,
            category=campaign_category,
            message_type=message_type,
            total_contacts=contacts_reached,
            status="queued"
        )
        db.add(campaign)
        db.flush() 

        # Deduct Credits
        old_credits = user.credits
        user.credits -= total_cost
        
        transaction = CreditTransaction(
            user_id=user.id,
            amount=-total_cost,
            type="usage",
            description=f"Campaign: {campaign.name} (Cost: {total_cost} credits)"
        )
        db.add(transaction)
        
        db.commit()
        db.refresh(user)
        logging.info(f"CREDIT_DEDUCTION: User {user.username} (Role: {user.role}) deducted {total_cost} credits. Old: {old_credits}, New: {user.credits}")

        count = 0
        for item in recipients:
            phone = item["phone"]
            row_data = item["metadata"]
            
            # Format text safely
            def format_text(txt):
                if not txt: return ""
                try:
                    return str(txt).format(**row_data) if "{" in str(txt) else str(txt)
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
                
                # Include campaign tracking in payload
                payload["campaign_id"] = campaign.id
                payload["user_id"] = user.id
                
                SEND_QUEUE.enqueue(payload, final_api_key)
                count += 1

        return {"status": "success", "messages_queued": count, "contacts_reached": contacts_reached}
    except Exception as e:
        logging.exception("Error during send-campaign")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)