#!/usr/bin/env python3
"""Request one daily draft from Render, then save it for the GitHub Pages frontend."""
import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from scripts.generate_editorial import (
    CONTENT_FILE,
    DISCLAIMER,
    IMAGE_DIR,
    NEWS_FILE,
    STATE_FILE,
    attempted_today,
    newest_unprocessed,
    read_json,
    write_json_atomic,
)

WIB = ZoneInfo("Asia/Jakarta")
RENDER_API_URL = "https://jatim-pijar-ai.onrender.com"
MAX_IMAGE_BYTES = 12 * 1024 * 1024


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _request, _file, _code, _message, _headers, _new_url):
        return None


def validate_render_url(value):
    parsed = urlparse(str(value or "").strip())
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname.endswith(".onrender.com") or parsed.path not in ("", "/"):
        raise SystemExit("RENDER_API_URL harus URL HTTPS service milik Render (.onrender.com).")
    return f"https://{hostname}"


def call_render(base_url, github_token, run_id, run_attempt, item):
    request = urllib.request.Request(
        f"{base_url}/internal/generate",
        data=json.dumps({"item": item}, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Run-ID": str(run_id),
            "X-GitHub-Run-Attempt": str(run_attempt),
        },
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=360) as response:
            raw = response.read(20 * 1024 * 1024 + 1)
            if len(raw) > 20 * 1024 * 1024:
                raise RuntimeError("Render mengembalikan respons yang terlalu besar.")
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Render menolak permintaan (HTTP {error.code}); periksa status service dan workflow.") from None
    except urllib.error.URLError:
        raise RuntimeError("Koneksi ke backend Render gagal.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("Respons backend Render tidak valid.") from None


def main():
    api_url = validate_render_url(RENDER_API_URL)
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "").strip()
    if not github_token or not run_id or not run_attempt:
        raise SystemExit("Skrip ini hanya boleh dijalankan dari GitHub Actions.")

    today = datetime.now(WIB).date().isoformat()
    state = read_json(STATE_FILE, {"last_attempt_local_date": None})
    if attempted_today(state, today):
        print("Batas harian tercapai: tidak ada permintaan ke Render kedua hari ini (WIB).")
        return

    news_payload = read_json(NEWS_FILE, {})
    content = read_json(CONTENT_FILE, {"updated_at": None, "last_generated_local_date": None, "items": []})
    news_items = news_payload.get("items", []) if isinstance(news_payload, dict) else []
    generated_items = content.get("items", []) if isinstance(content, dict) else []
    item = newest_unprocessed(news_items, generated_items)
    if not item:
        print("Tidak ada berita terbaru yang belum diproses; Render tidak dipanggil.")
        return

    # Lock the day before calling Render. The workflow commits this state even on a failed request.
    state["last_attempt_local_date"] = today
    write_json_atomic(STATE_FILE, state)

    result = call_render(api_url, github_token, run_id, run_attempt, item)
    if result.get("news_id") != item.get("id"):
        raise RuntimeError("Backend Render mengembalikan berita yang tidak sesuai.")
    headline = str(result.get("headline", "")).strip()
    narrative = str(result.get("narrative", "")).strip()
    extension = result.get("image_extension")
    mime_type = result.get("image_mime_type")
    if not headline or len(headline) > 180 or not narrative or len(narrative) > 3500:
        raise RuntimeError("Render mengembalikan draf kosong atau terlalu panjang.")
    if (extension, mime_type) not in ((".jpg", "image/jpeg"), (".png", "image/png")):
        raise RuntimeError("Render mengembalikan format gambar yang tidak diizinkan.")
    try:
        image_bytes = base64.b64decode(result.get("image_base64", ""), validate=True)
    except (ValueError, TypeError):
        raise RuntimeError("Data gambar dari Render tidak valid.") from None
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise RuntimeError("Ukuran gambar dari Render kosong atau melebihi batas.")
    if extension == ".jpg" and not image_bytes.startswith(b"\xff\xd8\xff"):
        raise RuntimeError("Data gambar dari Render bukan JPEG yang valid.")
    if extension == ".png" and not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("Data gambar dari Render bukan PNG yang valid.")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    image_name = f"{item['id']}{extension}"
    image_file = IMAGE_DIR / image_name
    temporary_image = image_file.with_suffix(image_file.suffix + ".tmp")
    temporary_image.write_bytes(image_bytes)
    temporary_image.replace(image_file)

    created_at = datetime.now(timezone.utc).isoformat()
    generated_items = [entry for entry in generated_items if entry.get("news_id") != item["id"]]
    generated_items.append({
        "news_id": item["id"],
        "headline": headline,
        "narrative": narrative,
        "region": item.get("region", "Jawa Timur"),
        "source": item.get("source", "RSS"),
        "source_url": item.get("link", ""),
        "published": item.get("published"),
        "image": f"assets/generated/{image_name}",
        "image_alt": "Ilustrasi editorial AI; bukan foto atau bukti kejadian.",
        "disclaimer": DISCLAIMER,
        "created_at": created_at,
        "status": "DRAF AI — PERIKSA FAKTA",
    })
    generated_items = generated_items[-30:]
    content.update({
        "updated_at": created_at,
        "last_generated_local_date": today,
        "items": generated_items,
        "note": DISCLAIMER,
    })
    write_json_atomic(CONTENT_FILE, content)

    keep_images = {Path(entry["image"]).name for entry in generated_items if entry.get("image")}
    for existing_image in IMAGE_DIR.glob("*.*"):
        if existing_image.name not in keep_images and existing_image.is_file():
            existing_image.unlink()
    print(f"Render membuat satu draf baru untuk berita {item['id']}.")


if __name__ == "__main__":
    main()
