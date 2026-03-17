import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pandas as pd
import io
import uvicorn
from app.queue_manager import SEND_QUEUE 

# Load environment variables for the default API Key
load_dotenv()
DEFAULT_API_KEY = os.getenv("WASENDER_API_KEY", "")

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/send-campaign")
async def handle_form(
    message_type: str = Form(...),
    api_key: str = Form(None),
    message: str = Form(None),
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

            formatted_msg = format_text(message)
            
            types = [t.strip() for t in message_type.split(',')]
            for t in types:
                if not t: continue
                payload = {"to": phone}
                
                if t == "text":
                    payload["text"] = formatted_msg
                elif t == "image":
                    payload["imageUrl"] = media_url
                    if formatted_msg: payload["text"] = formatted_msg
                elif t == "video":
                    payload["videoUrl"] = media_url
                    if formatted_msg: payload["text"] = formatted_msg
                elif t == "document":
                    payload["documentUrl"] = media_url
                    payload["fileName"] = document_name or "Document"
                    if formatted_msg: payload["text"] = formatted_msg
                elif t == "location":
                    if formatted_msg: payload["text"] = formatted_msg
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