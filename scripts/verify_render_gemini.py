#!/usr/bin/env python3
"""Verify Gemini API-key/model access via Render without generating text or images."""
import json
import os
import urllib.error
import urllib.request

RENDER_URL = "https://jatim-pijar-ai.onrender.com"


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _request, _file, _code, _message, _headers, _new_url):
        return None


def main():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "").strip()
    if not token or not run_id or not run_attempt:
        raise SystemExit("Jalankan hanya dari workflow verifikasi GitHub Actions.")

    request = urllib.request.Request(
        f"{RENDER_URL}/internal/verify-gemini",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Run-ID": run_id,
            "X-GitHub-Run-Attempt": run_attempt,
        },
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=60) as response:
            result = json.loads(response.read(16 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Render menolak pemeriksaan (HTTP {error.code}); tidak ada generasi dijalankan.") from None
    except (urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError):
        raise SystemExit("Pemeriksaan Render gagal; tidak ada generasi dijalankan.") from None

    print(json.dumps(result, ensure_ascii=False))
    if not result.get("key_accepted"):
        raise SystemExit("Gemini menolak key atau pemeriksaan katalog gagal; tidak ada generasi dijalankan.")
    if not result.get("text_model_available") or not result.get("image_model_available"):
        raise SystemExit("Salah satu model yang dikonfigurasi tidak tersedia untuk key ini; tidak ada generasi dijalankan.")
    print("Key dan kedua model tersedia. Ini hanya cek metadata; belum membuat teks atau gambar.")


if __name__ == "__main__":
    main()
