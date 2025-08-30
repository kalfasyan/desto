import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class PushbulletNotifier:
    def __init__(self, api_key: Optional[str] = None):
        # Priority: explicit arg -> env var -> persisted ~/.desto_config.json
        api_key = api_key or os.environ.get("DESTO_PUSHBULLET_API_KEY")
        if not api_key:
            try:
                cfg = Path.home() / ".desto_config.json"
                if cfg.exists():
                    data = json.loads(cfg.read_text())
                    api_key = data.get("pushbullet_api_key") or api_key
            except Exception:
                # Don't fail on config read errors
                pass
        self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    def notify(self, title: str, body: str) -> bool:
        """Send a push and return True/False. Also logs response details."""
        result = self.notify_with_response(title=title, body=body)
        return bool(result.get("ok"))

    def notify_with_response(self, title: str, body: str, device_iden: Optional[str] = None) -> dict:
        """Send a push and return a dict with response details.

        Returns: {ok: bool, status_code: int|None, body: str}
        """
        if not self.api_key:
            logger.debug("Pushbullet API key not configured")
            return {"ok": False, "status_code": None, "body": "api_key_missing"}

        url = "https://api.pushbullet.com/v2/pushes"
        headers = {
            "Access-Token": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {"type": "note", "title": title, "body": body}
        if device_iden:
            payload["device_iden"] = device_iden

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=5)
            status = resp.status_code
            text = resp.text
            # Log detailed response for debugging (headers + body)
            try:
                logger.debug("Pushbullet response headers: %s", dict(resp.headers))
            except Exception:
                logger.debug("Pushbullet response headers: <unavailable>")

            # Log body at debug level for full inspection; keep info/warn for status
            logger.debug("Pushbullet response body: %s", text)

            if status == 200:
                logger.info("Pushbullet notification sent (200)")
                return {"ok": True, "status_code": status, "body": text, "headers": dict(resp.headers)}
            else:
                logger.warning(f"Pushbullet failed ({status}): {text}")
                return {"ok": False, "status_code": status, "body": text, "headers": dict(resp.headers)}
        except Exception as e:
            logger.exception(f"Pushbullet notification error: {e}")
            return {"ok": False, "status_code": None, "body": str(e)}

    def get_devices(self) -> list:
        """Return a list of devices from Pushbullet for the configured account.

        Each device is a dict as returned by the API. Returns empty list on error or missing key.
        """
        if not self.api_key:
            return []
        try:
            url = "https://api.pushbullet.com/v2/devices"
            headers = {"Access-Token": self.api_key}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("devices", [])
            else:
                logger.debug(f"Failed to list Pushbullet devices ({resp.status_code}): {resp.text}")
                return []
        except Exception as e:
            logger.debug(f"Exception listing Pushbullet devices: {e}")
            return []


_notifier = PushbulletNotifier()


def notify_job_finished(session_name: str, exit_code: int, finished_at: Optional[str] = None) -> bool:
    title = f"Job finished: {session_name}"
    body = f"Session: {session_name}\nExit code: {exit_code}"
    if finished_at:
        body += f"\nFinished at: {finished_at}"
    body += f"\n\nSent at: {datetime.utcnow().isoformat()}Z"

    # Attempt to target a specific active device for better mobile delivery.
    try:
        devices = _notifier.get_devices()
        device_iden = None
        chosen_device = None
        if devices:
            # Prefer mobile devices (android / ios) first for push notifications.
            # Pushbullet device objects sometimes include the platform in a
            # `kind` field and sometimes in a `type` field. In practice both
            # fields contain the same canonical values for mobile devices, so
            # use one set and check both fields against it.
            mobile_platforms = {"android", "ios", "iphone"}

            # Find active mobile device
            for d in devices:
                kind = (d.get("kind") or "").lower()
                dtype = (d.get("type") or "").lower()
                if d.get("active") and d.get("iden") and (kind in mobile_platforms or dtype in mobile_platforms):
                    device_iden = d.get("iden")
                    chosen_device = d
                    break

            # If no active mobile device, fall back to any active device with iden
            if not device_iden:
                for d in devices:
                    if d.get("active") and d.get("iden"):
                        device_iden = d.get("iden")
                        chosen_device = d
                        break

        if device_iden:
            logger.info(f"notify_job_finished: sending push to device {device_iden} ({chosen_device.get('nickname')})")
            resp = _notifier.notify_with_response(title=title, body=body, device_iden=device_iden)
        else:
            logger.info("notify_job_finished: no device_iden found, sending broadcast push")
            resp = _notifier.notify_with_response(title=title, body=body)

        # Log the full response at info level so external scripts can see output
        logger.info("notify_job_finished response: %s", resp)
        # Return the full response dict (previously returned a bool). Callers may inspect 'ok' or other fields.
        return resp
    except Exception as e:
        logger.exception("notify_job_finished exception: %s", e)
        return False
