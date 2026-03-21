import requests
import time
import threading
import queue
import logging
import os
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Campaign, CampaignLog
from datetime import datetime

logger = logging.getLogger(__name__)

class WasenderQueue:
    def __init__(self, api_base: str, max_retries=5, pause_after_success=0.4):
        self.api_base = api_base.rstrip("/") + "/api/send-message"
        self.session = requests.Session()
        self.queue = queue.Queue()
        self.max_retries = max_retries
        self.pause_after_success = pause_after_success
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        logger.info("WasenderQueue started, sending to %s", self.api_base)

    def enqueue(self, payload: dict, api_key: str):
        payload["_api_key"] = api_key
        payload["_enqueued_at"] = time.time()
        # Keep internal metadata keys like _api_key, user_id, campaign_id
        self.queue.put(payload)
        return True

    def _worker(self):
        while True:
            payload = self.queue.get()
            try:
                self._process_payload(payload)
            except Exception as e:
                logger.exception("Unexpected worker error: %s", e)
            finally:
                self.queue.task_done()

    def _process_payload(self, payload: dict):
        api_key = payload.pop("_api_key", "")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        # Clean internal keys for the external API but keep them for our logging
        send_payload = {k: v for k, v in payload.items() if not k.startswith("_") and k not in ["user_id", "campaign_id"]}
        logger.info("[SEND] Sending payload to API: %s", send_payload)
        
        campaign_id = payload.get("campaign_id")
        user_id = payload.get("user_id")
        to_phone = payload.get("to")

        db: Session = SessionLocal()
        
        attempt = 0
        delay = 1.0
        max_attempts = payload.get("_max_retries", self.max_retries)
        
        success = False
        error_msg = None

        while attempt < max_attempts:
            attempt += 1
            try:
                r = self.session.post(self.api_base, json=send_payload, headers=headers, timeout=15)
                status = r.status_code
                if status < 300:
                    logger.info("[SUCCESS] Message sent to %s (attempt %d).", to_phone, attempt)
                    success = True
                    break # Success!
                
                error_msg = f"HTTP {status}: {r.text[:200]}"
                if status == 429:
                    logger.warning("[RATE-LIMIT] Rate limited sending to %s. Retrying in %ds", to_phone, int(delay))
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue
                
                if 500 <= status < 600:
                    logger.warning("Server error %s. Retrying in %ds.", status, int(delay))
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue

                logger.error("Failed to send to %s: status=%s, resp=%s", to_phone, status, r.text[:400])
                break # Non-retryable error
            except Exception as e:
                error_msg = str(e)
                logger.warning("Error sending to %s: %s. Retrying in %ds", to_phone, e, int(delay))
                time.sleep(delay)
                delay = min(delay * 2, 30)

        # Logging to Campaign Database
        if campaign_id:
            try:
                # Log detail
                log_entry = CampaignLog(
                    campaign_id=campaign_id,
                    phone=to_phone,
                    status="success" if success else "failure",
                    error_message=None if success else error_msg
                )
                db.add(log_entry)
                
                # Update Campaign totals
                campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
                if campaign:
                    campaign.processed_count += 1
                    if success:
                        campaign.success_count += 1
                    else:
                        campaign.failure_count += 1
                    
                    # If finished, update status and timestamp
                    if campaign.processed_count >= campaign.total_contacts:
                        campaign.status = "completed"
                        campaign.completed_at = datetime.now()
                
                db.commit()
            except Exception as ex:
                logger.error("Failed to update campaign DB: %s", ex)
                db.rollback()
            finally:
                db.close()

        if success and self.pause_after_success:
            time.sleep(self.pause_after_success)
        
        if not success:
            logger.error("[FAILED] Giving up after %d attempts for %s", max_attempts, to_phone)

# Global instance
SEND_QUEUE = WasenderQueue(api_base="https://www.wasenderapi.com", max_retries=5, pause_after_success=0.4)