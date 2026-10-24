#!/usr/bin/env python3
"""GitHub Actions-authenticated Gemini generation endpoint for Render."""
import base64
import hmac
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from scripts.generate_editorial import generate_image, generate_narrative

MAX_REQUEST_BYTES = 32 * 1024
GITHUB_REPO = "shopppit1-tech/jatim-pijar"
GENERATION_WORKFLOW = ".github/workflows/generate-daily-content.yml"
GEMINI_VERIFY_WORKFLOW = ".github/workflows/verify-gemini-key.yml"
GITHUB_API = "https://api.github.com"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
TEXT_MODEL = "gemini-3.8-flash"
IMAGE_MODEL = "gemini-nano-banana-2.1"
WIB = ZoneInfo("Asia/Jakarta")
_generation_lock = threading.Lock()
_last_attempt_local_date = None


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _request, _file, _code, _message, _headers, _new_url):
        return None


def github_api_get(path, token):
    request = urllib.request.Request(
        f"{GITHUB_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "JatimPijar-Render-Backend",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(NoRedirectHandler())
    with opener.open(request, timeout=15) as response:
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("GitHub response too large")
        return json.loads(raw.decode("utf-8"))


def verify_github_action(token, run_id, run_attempt):
    """Require a repo-scoped GitHub Actions token and the expected active workflow run."""
    if not token or not re.fullmatch(r"[0-9]{1,20}", str(run_id or "")):
        return False
    if not re.fullmatch(r"[0-9]{1,6}", str(run_attempt or "")):
        return False
    try:
        installation = github_api_get("/installation/repositories?per_page=100", token)
        allowed_repositories = {
            repo.get("full_name") for repo in installation.get("repositories", [])
            if isinstance(repo, dict)
        }
        if GITHUB_REPO not in allowed_repositories:
            return False
        run = github_api_get(f"/repos/{GITHUB_REPO}/actions/runs/{run_id}", token)
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return False

    repository = run.get("repository") or {}
    return (
        str(run.get("id")) == str(run_id)
        and str(run.get("run_attempt")) == str(run_attempt)
        and repository.get("full_name") == GITHUB_REPO
        and run.get("path") in (GENERATION_WORKFLOW, GEMINI_VERIFY_WORKFLOW)
        and run.get("head_branch") == "main"
        and run.get("event") in ("schedule", "workflow_dispatch")
        and run.get("status") == "in_progress"
    )


def verify_gemini_access(api_key):
    """Check API-key acceptance and configured model availability without generating content."""
    def get_json(url):
        request = urllib.request.Request(
            url,
            headers={"x-goog-api-key": api_key, "Accept": "application/json"},
            method="GET",
        )
        opener = urllib.request.build_opener(NoRedirectHandler())
        try:
            with opener.open(request, timeout=15) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    return response.status, {}
                return response.status, json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, {}
        except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError, TimeoutError):
            return 0, {}

    list_status, catalog = get_json(f"{GEMINI_API}/models?pageSize=1000")
    if list_status != 200:
        return {
            "key_accepted": False,
            "http_status": list_status,
            "text_model_available": False,
            "image_model_available": False,
        }

    available_names = set()
    for model in catalog.get("models", []):
        if not isinstance(model, dict):
            continue
        for field in ("name", "baseModelId"):
            value = str(model.get(field, "")).removeprefix("models/")
            if value:
                available_names.add(value)
    return {
        "key_accepted": True,
        "http_status": 200,
        "text_model_available": TEXT_MODEL in available_names,
        "image_model_available": IMAGE_MODEL in available_names,
    }


def reserve_generation_day(today):
    """Defense in depth per process; the workflow's committed state is the durable daily lock."""
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
            endpoint = urlparse(self.path).path
            if endpoint not in ("/internal/generate", "/internal/verify-gemini"):
                self.send_json(404, {"error": "not found"})
                return

            supplied_auth = self.headers.get("Authorization", "")
            if not supplied_auth.startswith("Bearer "):
                self.send_json(401, {"error": "unauthorized"})
                return
            github_token = supplied_auth[len("Bearer "):].strip()
            run_id = self.headers.get("X-GitHub-Run-ID", "")
            run_attempt = self.headers.get("X-GitHub-Run-Attempt", "")
            if not verify_github_action(github_token, run_id, run_attempt):
                self.send_json(401, {"error": "unauthorized"})
                return

            api_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not api_key:
                self.send_json(503, {"error": "Gemini is not configured"})
                return

            if endpoint == "/internal/verify-gemini":
                self.send_json(200, verify_gemini_access(api_key))
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
            except Exception as error:
                detail = str(error).splitlines()[0][:180] if isinstance(error, RuntimeError) else type(error).__name__
                logging.warning("Gemini text step failed (%s): %s", type(error).__name__, detail)
                self.send_json(502, {"error": "text generation failed"})
                return

            try:
                with _generation_lock:
                    image_bytes, extension = generate_image(api_key, item)
            except Exception as error:
                detail = str(error).splitlines()[0][:180] if isinstance(error, RuntimeError) else type(error).__name__
                logging.warning("Gemini image step failed (%s): %s", type(error).__name__, detail)
                self.send_json(502, {"error": "image generation failed"})
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
