#!/usr/bin/env python3
"""Private-token-protected Gemini generation endpoint for the Render web service."""
import base64
import hmac
import json
import logging
import os
import re
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from scripts.generate_editorial import generate_image, generate_narrative

MAX_REQUEST_BYTES = 32 * 1024
WIB = ZoneInfo("Asia/Jakarta")
_generation_lock = threading.Lock()
_last_attempt_local_date = None


def reserve_generation_day(today):
    """Defense in depth per process; GitHub's committed state is the durable daily lock."""
    global _last_attempt_local_date
    with _generation_lock:
        if _last_attempt_local_date == today:
            return False
        _last_attempt_local_date = today
        return True


def normalize_item(value):
    if not isinstance(value, dict):
        raise ValueError("invalid payload")
    news_id = str(value.get("id", "")).strip()
    title = str(value.get("title", "")).strip()
    if not re.fullmatch(r"[a-f0-9]{16}", news_id) or not title or len(title) > 500:
        raise ValueError("invalid story")
    link = str(value.get("link", "")).strip()
    if link:
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("invalid source link")
    return {
        "id": news_id,
        "title": title,
        "description_context": str(value.get("description_context", ""))[:1200],
        "region": str(value.get("region", "Jawa Timur"))[:100],
        "source": str(value.get("source", "RSS"))[:200],
        "link": link[:2000],
        "published": str(value.get("published", ""))[:80],
    }


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        server_version = "JatimPijarBackend"
        sys_version = ""

        def log_message(self, _format, *_args):
            # Keep request bodies, authorization headers, and provider details out of logs.
            return

        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path == "/health":
                self.send_json(200, {"status": "ok"})
            else:
                self.send_json(404, {"error": "not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/internal/generate":
                self.send_json(404, {"error": "not found"})
                return

            expected_secret = os.environ.get("RENDER_WEBHOOK_SECRET", "")
            supplied_auth = self.headers.get("Authorization", "")
            expected_auth = f"Bearer {expected_secret}" if expected_secret else ""
            if not expected_secret or not hmac.compare_digest(
                supplied_auth.encode("utf-8"), expected_auth.encode("utf-8")
            ):
                self.send_json(401, {"error": "unauthorized"})
                return

            api_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not api_key:
                self.send_json(503, {"error": "Gemini is not configured"})
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length < 1 or length > MAX_REQUEST_BYTES:
                self.send_json(413, {"error": "invalid request size"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                item = normalize_item(payload.get("item"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, AttributeError):
                self.send_json(400, {"error": "invalid request"})
                return

            today = datetime.now(WIB).date().isoformat()
            if not reserve_generation_day(today):
                self.send_json(409, {"error": "daily generation limit reached"})
                return

            try:
                with _generation_lock:
                    headline, narrative = generate_narrative(api_key, item)
                    image_bytes, extension = generate_image(api_key, item)
            except Exception as error:
                logging.warning("Gemini generation failed (%s).", type(error).__name__)
                self.send_json(502, {"error": "generation failed; retry on the next daily window"})
                return

            mime_type = "image/jpeg" if extension == ".jpg" else "image/png"
            self.send_json(200, {
                "news_id": item["id"],
                "headline": headline,
                "narrative": narrative,
                "image_base64": base64.b64encode(image_bytes).decode("ascii"),
                "image_extension": extension,
                "image_mime_type": mime_type,
            })

    return Handler


def main():
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler())
    logging.info("JatimPijar backend listening on port %s", port)
    server.serve_forever()


if __name__ == "__main__":
    main()
