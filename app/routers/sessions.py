from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.auth import get_current_active_user_or_401
from app.wasender_utils import wa_api
import logging

router = APIRouter(prefix="/sessions", tags=["WhatsApp Sessions"])

@router.get("/status")
async def get_session_status(
    current_user: User = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    if not current_user.whatsapp_session_id:
        return {"status": "disconnected", "message": "No session created."}
    
    try:
        status_resp = await wa_api.get_status(current_user.whatsapp_session_id)
        logging.info(f"Session status response: {status_resp}")
        
        # WASender often nests everything in a "data" object
        data = status_resp.get("data", status_resp)
        
        # If the API returns 404 or an error, handle it
        if "id" not in data:
             return {"status": "disconnected", "message": "Session not found on server.", "raw": status_resp}
        
        # Mapping WASender status to our local status
        remote_status = data.get("status", "disconnected")
        current_user.whatsapp_session_status = remote_status
        
        # If the response contains an API key, we should store it for message sending
        if "api_key" in data:
            current_user.custom_api_key = data["api_key"]
            
        db.commit()
        
        return {"status": remote_status, "session_id": current_user.whatsapp_session_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/connect")
async def connect_session(
    phone_number: str,
    current_user: User = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    try:
        # If session doesn't exist, create it
        if not current_user.whatsapp_session_id:
            session_name = f"user_{current_user.id}_{current_user.username}"
            logging.info(f"Creating session: {session_name} for phone: {phone_number}")
            resp = await wa_api.create_session(session_name, phone_number)
            logging.info(f"Create session response: {resp}")
            
            # WASender response might have "data" field wrapping the result
            data = resp.get("data", resp)
            if "id" in data:
                current_user.whatsapp_session_id = data["id"]
                db.commit()
            else:
                logging.error(f"Failed to create session: {resp}")
                raise HTTPException(status_code=422, detail=f"Failed to create session: {resp}")

        # Initiate connection if needed
        logging.info(f"Initiating connection for session: {current_user.whatsapp_session_id}")
        conn_resp = await wa_api.initiate_connect(current_user.whatsapp_session_id)
        logging.info(f"Initiate connection response: {conn_resp}")

        # Fetch QR code
        logging.info(f"Fetching QR code for session: {current_user.whatsapp_session_id}")
        qr_resp = await wa_api.get_qr_code(current_user.whatsapp_session_id)
        logging.info(f"QR code response: {qr_resp}")
        
        # WASender often nests everything in a "data" object
        data = qr_resp.get("data", qr_resp)
        qr_code = data.get("qrCode") or data.get("qrcode") or qr_resp.get("qrcode")
        
        if not qr_code:
            logging.error(f"Failed to get QR code from response: {qr_resp}")
            return {"error": "QR code not found in response", "raw": qr_resp}

        return {"qrcode": qr_code, "status": data.get("status")}
    except Exception as e:
        logging.exception("Error in connect_session")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete")
async def delete_session(
    current_user: User = Depends(get_current_active_user_or_401),
    db: Session = Depends(get_db)
):
    if current_user.whatsapp_session_id:
        await wa_api.delete_session(current_user.whatsapp_session_id)
        current_user.whatsapp_session_id = None
        current_user.whatsapp_session_status = "disconnected"
        db.commit()
        return {"status": "success", "message": "Session deleted."}
    return {"status": "error", "message": "No session to delete."}
