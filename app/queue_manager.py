import requests
import time
import threading
import queue
import logging

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
        
        # Clean internal keys
        send_payload = {k: v for k, v in payload.items() if not k.startswith("_")}
        logger.info("[SEND] Sending payload to API: %s", send_payload)
        
        attempt = 0
        delay = 1.0
        max_attempts = payload.get("_max_retries", self.max_retries)

        while attempt < max_attempts:
            attempt += 1
            try:
                r = self.session.post(self.api_base, json=send_payload, headers=headers, timeout=15)
                status = r.status_code
                if status < 300:
                    logger.info("[SUCCESS] Message sent to %s (attempt %d).", payload.get("to"), attempt)
                    if self.pause_after_success:
                        time.sleep(self.pause_after_success)
                    return
                
                if status == 429:
                    logger.warning("[RATE-LIMIT] Rate limited sending to %s. Retrying in %ds", payload.get("to"), int(delay))
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue
                
                if 500 <= status < 600:
                    logger.warning("Server error %s. Retrying in %ds.", status, int(delay))
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue

                logger.error("Failed to send to %s: status=%s, resp=%s", payload.get("to"), status, r.text[:400])
                return
            except requests.exceptions.RequestException as e:
                logger.warning("Network error sending to %s: %s. Retrying in %ds", payload.get("to"), e, int(delay))
                time.sleep(delay)
                delay = min(delay * 2, 30)

        logger.error("[FAILED] Giving up after %d attempts for %s", max_attempts, payload.get("to"))

# Global instance
SEND_QUEUE = WasenderQueue(api_base="https://www.wasenderapi.com", max_retries=5, pause_after_success=0.4)