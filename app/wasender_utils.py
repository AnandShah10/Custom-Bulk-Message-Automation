import os
import httpx
from dotenv import load_dotenv

load_dotenv()

WASENDER_BASE_URL = "https://wasenderapi.com"
WASENDER_PERSONAL_TOKEN = os.getenv("WASENDER_PERSONAL_TOKEN")

class WASenderAPI:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {WASENDER_PERSONAL_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def get_sessions(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{WASENDER_BASE_URL}/api/whatsapp-sessions", headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def create_session(self, name: str, phone_number: str, account_protection: bool = True):
        payload = {
            "name": name,
            "phone_number": phone_number,
            "account_protection": account_protection,
            "log_messages": True,
            "webhook_enabled": False
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{WASENDER_BASE_URL}/api/whatsapp-sessions", json=payload, headers=self.headers)
            if response.status_code not in [200, 201]:
                return {"error": response.status_code, "detail": response.text}
            return response.json()

    async def get_qr_code(self, session_id: str):
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{WASENDER_BASE_URL}/api/whatsapp-sessions/{session_id}/qrcode", headers=self.headers)
            if response.status_code != 200:
                return {"error": response.status_code, "detail": response.text}
            return response.json()

    async def initiate_connect(self, session_id: str):
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{WASENDER_BASE_URL}/api/whatsapp-sessions/{session_id}/connect", headers=self.headers)
            if response.status_code not in [200, 201]:
                return {"error": response.status_code, "detail": response.text}
            return response.json()

    async def get_status(self, session_id: str):
        # The docs show GET /api/status returns the status of the "connected" session. 
        # But we need status for a specific session ID if managing multiple.
        # Let's use GET /api/whatsapp-sessions/{session_id} to get details including status.
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{WASENDER_BASE_URL}/api/whatsapp-sessions/{session_id}", headers=self.headers)
            return response.json()

    async def delete_session(self, session_id: str):
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{WASENDER_BASE_URL}/api/whatsapp-sessions/{session_id}", headers=self.headers)
            if response.status_code == 204 or not response.content:
                return {"success": True, "message": "Session deleted (no content)"}
            try:
                return response.json()
            except:
                return {"success": response.is_success, "status_code": response.status_code, "text": response.text}

wa_api = WASenderAPI()
