import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest import mock

import scripts.fetch_news as fetch_news
import scripts.generate_editorial as generate_editorial
import scripts.request_render_generation as request_render_generation
import render_service
from scripts.fetch_news import editorial_headline, make_post, stable_id
from scripts.generate_editorial import attempted_today, extract_image, extract_text, newest_unprocessed, parse_json_object


class FetchNewsTests(unittest.TestCase):
    def test_render_request_script_imports_when_executed_directly(self):
        environment = os.environ.copy()
        for name in ("GITHUB_TOKEN", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
            environment.pop(name, None)
        script = Path(request_render_generation.__file__)
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=script.parents[1],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Skrip ini hanya boleh dijalankan dari GitHub Actions", result.stderr)
        self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_id_is_stable_and_link_specific(self):
        first = stable_id("https://example.com/news/1")
        self.assertEqual(first, stable_id("https://example.com/news/1"))
        self.assertNotEqual(first, stable_id("https://example.com/news/2"))
        self.assertEqual(len(first), 16)

    def test_post_is_labeled_as_metadata_based_draft(self):
        post = make_post({
            "region": "Surabaya",
            "title": "Contoh kabar",
            "source": "Contoh Sumber",
            "published": "2026-10-24T00:00:00+00:00",
            "link": "https://example.com/article",
        })
        self.assertIn("Pantauan Surabaya", post)
        self.assertIn("metadata RSS", post)
        self.assertIn("Contoh Sumber", post)
        self.assertNotIn("https://example.com/article", post)

    def test_editorial_headline_strips_publisher_suffix(self):
        self.assertEqual(
            editorial_headline({"region": "Gresik", "title": "Ada peristiwa - Contoh Media"}),
            "Pantauan Gresik: Ada peristiwa",
        )

    def test_total_feed_outage_keeps_last_good_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news = root / "news.json"
            content = root / "content.json"
            news.write_text(json.dumps({"updated_at": "lama", "items": [{"id": "lama"}]}), encoding="utf-8")
            content.write_text('{"items": ["lama"]}', encoding="utf-8")
            original_news = news.read_text(encoding="utf-8")
            original_content = content.read_text(encoding="utf-8")
            with mock.patch.object(fetch_news, "ROOT", root), \
                 mock.patch.object(fetch_news, "QUERIES", [("Surabaya", "Surabaya")]), \
                 mock.patch.object(fetch_news.urllib.request, "urlopen", side_effect=OSError("offline")), \
                 mock.patch.object(fetch_news.time, "sleep"):
                with self.assertRaises(SystemExit):
                    fetch_news.main()
            self.assertEqual(news.read_text(encoding="utf-8"), original_news)
            self.assertEqual(content.read_text(encoding="utf-8"), original_content)

    def test_daily_limit_uses_wib_attempt_date(self):
        self.assertTrue(attempted_today({"last_attempt_local_date": "2026-10-24"}, "2026-10-24"))
        self.assertFalse(attempted_today({"last_attempt_local_date": "2026-10-23"}, "2026-10-24"))

    def test_only_latest_unprocessed_story_is_selected(self):
        stories = [
            {"id": "old", "published": "2026-10-23T00:00:00Z"},
            {"id": "new", "published": "2026-10-24T00:00:00Z"},
        ]
        self.assertEqual(newest_unprocessed(stories, [])["id"], "new")
        self.assertIsNone(newest_unprocessed(stories, [{"news_id": "new"}]))

    def test_parses_text_and_image_from_interaction_steps(self):
        response = {"steps": [{"type": "model_output", "content": [
            {"type": "text", "text": "narasi"},
            {"type": "image", "data": "aW1hZ2U=", "mime_type": "image/jpeg"},
        ]}]}
        self.assertEqual(extract_text(response), "narasi")
        self.assertEqual(extract_image(response), ("aW1hZ2U=", "image/jpeg"))
        self.assertEqual(extract_text({"output_text": "teks langsung"}), "teks langsung")
        self.assertEqual(extract_image({"output_image": {"data": "cG5n", "mime_type": "image/png"}}),
                         ("cG5n", "image/png"))

    def test_json_parser_accepts_prefix_and_suffix_but_rejects_invalid(self):
        self.assertEqual(parse_json_object('Hasil:\n{"headline":"A","narrative":"B"}\nSelesai.'),
                         {"headline": "A", "narrative": "B"})
        with self.assertRaises(RuntimeError):
            parse_json_object("teks tanpa objek JSON")

    def test_generation_is_two_calls_then_rerun_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news_file = root / "news.json"
            content_file = root / "generated_content.json"
            state_file = root / "generation_state.json"
            image_dir = root / "assets" / "generated"
            news_file.write_text(json.dumps({"items": [{
                "id": "0123456789abcdef", "title": "Contoh berita", "region": "Surabaya",
                "source": "Contoh RSS", "link": "https://example.com/news",
                "published": "2026-10-24T00:00:00+00:00", "description_context": "Cuplikan berita.",
            }]}), encoding="utf-8")
            content_file.write_text(json.dumps({"items": []}), encoding="utf-8")
            image_data = base64.b64encode(b"\xff\xd8\xfffake-jpeg").decode("ascii")
            responses = [
                {"steps": [{"type": "model_output", "content": [{
                    "type": "text", "text": json.dumps({"headline": "Judul baru", "narrative": "Narasi draf."}),
                }]}]},
                {"steps": [{"type": "model_output", "content": [{
                    "type": "image", "data": image_data, "mime_type": "image/jpeg",
                }]}]},
            ]
            with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-only-not-a-real-key"}), \
                 mock.patch.object(generate_editorial, "NEWS_FILE", news_file), \
                 mock.patch.object(generate_editorial, "CONTENT_FILE", content_file), \
                 mock.patch.object(generate_editorial, "STATE_FILE", state_file), \
                 mock.patch.object(generate_editorial, "IMAGE_DIR", image_dir), \
                 mock.patch.object(generate_editorial, "call_gemini", side_effect=responses) as api_call:
                generate_editorial.main()
                generate_editorial.main()
            self.assertEqual(api_call.call_count, 2)
            text_request = api_call.call_args_list[0].args[1]
            image_request = api_call.call_args_list[1].args[1]
            self.assertEqual(text_request["model"], generate_editorial.TEXT_MODEL)
            self.assertEqual(image_request["model"], generate_editorial.IMAGE_MODEL)
            self.assertIs(text_request["store"], False)
            self.assertIs(image_request["store"], False)
            generated = json.loads(content_file.read_text(encoding="utf-8"))
            self.assertEqual(len(generated["items"]), 1)
            self.assertTrue((image_dir / "0123456789abcdef.jpg").exists())

    def test_failed_generation_persists_daily_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news_file = root / "news.json"
            content_file = root / "generated_content.json"
            state_file = root / "generation_state.json"
            news_file.write_text(json.dumps({"items": [{
                "id": "0123456789abcdef", "title": "Contoh berita", "published": "2026-10-24T00:00:00Z",
            }]}), encoding="utf-8")
            content_file.write_text(json.dumps({"items": []}), encoding="utf-8")
            text_response = {"steps": [{"type": "model_output", "content": [{
                "type": "text", "text": json.dumps({"headline": "Judul", "narrative": "Narasi"}),
            }]}]}
            with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-only-not-a-real-key"}), \
                 mock.patch.object(generate_editorial, "NEWS_FILE", news_file), \
                 mock.patch.object(generate_editorial, "CONTENT_FILE", content_file), \
                 mock.patch.object(generate_editorial, "STATE_FILE", state_file), \
                 mock.patch.object(generate_editorial, "IMAGE_DIR", root / "assets" / "generated"), \
                 mock.patch.object(generate_editorial, "call_gemini", side_effect=[text_response, RuntimeError("simulated")]) as api_call:
                with self.assertRaises(RuntimeError):
                    generate_editorial.main()
                generate_editorial.main()
            self.assertEqual(api_call.call_count, 2)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["last_attempt_local_date"], datetime.now(generate_editorial.WIB).date().isoformat())

    def test_missing_secret_does_not_call_api(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch.object(generate_editorial, "call_gemini") as api_call:
            with self.assertRaises(SystemExit):
                generate_editorial.main()
        api_call.assert_not_called()

    def test_processed_latest_story_does_not_call_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news_file = root / "news.json"
            content_file = root / "generated_content.json"
            news_file.write_text(json.dumps({"items": [{
                "id": "0123456789abcdef", "title": "Sudah diproses", "published": "2026-10-24T00:00:00Z",
            }]}), encoding="utf-8")
            content_file.write_text(json.dumps({"items": [{"news_id": "0123456789abcdef"}]}), encoding="utf-8")
            with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-only-not-a-real-key"}), \
                 mock.patch.object(generate_editorial, "NEWS_FILE", news_file), \
                 mock.patch.object(generate_editorial, "CONTENT_FILE", content_file), \
                 mock.patch.object(generate_editorial, "STATE_FILE", root / "state.json"), \
                 mock.patch.object(generate_editorial, "call_gemini") as api_call:
                generate_editorial.main()
            api_call.assert_not_called()

    def test_render_url_requires_https_on_render_domain(self):
        self.assertEqual(
            request_render_generation.validate_render_url("https://jatim-pijar-ai.onrender.com/"),
            "https://jatim-pijar-ai.onrender.com",
        )
        with self.assertRaises(SystemExit):
            request_render_generation.validate_render_url("http://jatim-pijar-ai.onrender.com")
        with self.assertRaises(SystemExit):
            request_render_generation.validate_render_url("https://example.com")

    def test_gemini_redirect_is_disabled_to_protect_api_key(self):
        handler = generate_editorial.NoRedirectHandler()
        request = request_render_generation.urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/interactions"
        )
        self.assertIsNone(handler.redirect_request(
            request, None, 302, "Found", {}, "https://attacker.example/collect"
        ))

    def test_render_request_sends_actions_token_and_run_metadata(self):
        response_payload = {"status": "ok"}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(response_payload).encode("utf-8")

        class Opener:
            request = None

            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()

        opener = Opener()
        item = {"id": "0123456789abcdef", "title": "Kabar", "link": "https://example.com"}
        with mock.patch.object(request_render_generation.urllib.request, "build_opener", return_value=opener):
            result = request_render_generation.call_render(
                "https://jatim-pijar-ai.onrender.com", "test-github-actions-token", "12345", "1", item
            )
        self.assertEqual(result, response_payload)
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer test-github-actions-token")
        self.assertEqual(opener.request.get_header("X-github-run-id"), "12345")
        self.assertEqual(opener.request.get_header("X-github-run-attempt"), "1")
        self.assertEqual(opener.request.full_url, "https://jatim-pijar-ai.onrender.com/internal/generate")
        self.assertNotIn(b"GEMINI_API_KEY", opener.request.data)

    def test_render_backend_rejects_invalid_story_payload(self):
        with self.assertRaises(ValueError):
            render_service.normalize_item({"id": "bad", "title": "Kabar"})
        with self.assertRaises(ValueError):
            render_service.normalize_item({
                "id": "0123456789abcdef", "title": "Kabar", "link": "javascript:alert(1)"
            })

    def test_render_process_has_secondary_daily_limit(self):
        with mock.patch.object(render_service, "_last_attempt_local_date", None):
            self.assertTrue(render_service.reserve_generation_day("2026-10-24"))
            self.assertFalse(render_service.reserve_generation_day("2026-10-24"))
            self.assertTrue(render_service.reserve_generation_day("2026-10-25"))

    def test_render_backend_requires_expected_active_github_workflow(self):
        installation = {"repositories": [{"full_name": render_service.GITHUB_REPO}]}
        run = {
            "id": 12345,
            "run_attempt": 1,
            "repository": {"full_name": render_service.GITHUB_REPO},
            "path": render_service.GENERATION_WORKFLOW,
            "head_branch": "main",
            "event": "schedule",
            "status": "in_progress",
        }
        with mock.patch.object(render_service, "github_api_get", side_effect=[installation, run]):
            self.assertTrue(render_service.verify_github_action("test-token", "12345", "1"))
        run["path"] = render_service.GEMINI_VERIFY_WORKFLOW
        run["event"] = "workflow_dispatch"
        with mock.patch.object(render_service, "github_api_get", side_effect=[installation, run]):
            self.assertTrue(render_service.verify_github_action("test-token", "12345", "1"))
        run["path"] = ".github/workflows/other.yml"
        with mock.patch.object(render_service, "github_api_get", side_effect=[installation, run]):
            self.assertFalse(render_service.verify_github_action("test-token", "12345", "1"))

    def test_gemini_access_check_lists_models_without_generation(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({"models": [
                    {"name": f"models/{render_service.TEXT_MODEL}"},
                    {"name": f"models/{render_service.IMAGE_MODEL}"},
                ]}).encode("utf-8")

        class Opener:
            request = None

            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()

        opener = Opener()
        with mock.patch.object(render_service.urllib.request, "build_opener", return_value=opener):
            result = render_service.verify_gemini_access("test-key-not-real")
        self.assertTrue(result["key_accepted"])
        self.assertTrue(result["text_model_available"])
        self.assertTrue(result["image_model_available"])
        self.assertEqual(opener.request.get_method(), "GET")
        self.assertTrue(opener.request.full_url.endswith("/models?pageSize=1000"))
        self.assertEqual(opener.request.get_header("X-goog-api-key"), "test-key-not-real")

    def test_gemini_access_check_reports_rejected_key_without_body(self):
        class Opener:
            def open(self, _request, timeout):
                raise urllib.error.HTTPError("https://example.com", 403, "Forbidden", {}, None)

        with mock.patch.object(render_service.urllib.request, "build_opener", return_value=Opener()):
            result = render_service.verify_gemini_access("test-key-not-real")
        self.assertEqual(result["http_status"], 403)
        self.assertFalse(result["key_accepted"])
        self.assertFalse(result["image_model_available"])

    def test_render_workflow_saves_one_result_and_blocks_same_day_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news_file = root / "news.json"
            content_file = root / "generated_content.json"
            state_file = root / "generation_state.json"
            image_dir = root / "assets" / "generated"
            news_file.write_text(json.dumps({"items": [{
                "id": "0123456789abcdef", "title": "Berita baru", "region": "Surabaya",
                "source": "RSS", "link": "https://example.com/news", "published": "2026-10-24T00:00:00Z",
                "description_context": "Cuplikan RSS.",
            }]}), encoding="utf-8")
            content_file.write_text(json.dumps({"items": []}), encoding="utf-8")
            image_data = base64.b64encode(b"\xff\xd8\xfffake-jpeg").decode("ascii")
            result = {
                "news_id": "0123456789abcdef", "headline": "Judul draf", "narrative": "Narasi draf.",
                "image_base64": image_data, "image_extension": ".jpg", "image_mime_type": "image/jpeg",
            }
            with mock.patch.dict("os.environ", {
                "GITHUB_TOKEN": "test-github-actions-token",
                "GITHUB_RUN_ID": "12345",
                "GITHUB_RUN_ATTEMPT": "1",
            }), mock.patch.object(request_render_generation, "NEWS_FILE", news_file), \
                 mock.patch.object(request_render_generation, "CONTENT_FILE", content_file), \
                 mock.patch.object(request_render_generation, "STATE_FILE", state_file), \
                 mock.patch.object(request_render_generation, "IMAGE_DIR", image_dir), \
                 mock.patch.object(request_render_generation, "call_render", return_value=result) as render_call:
                request_render_generation.main()
                request_render_generation.main()
            self.assertEqual(render_call.call_count, 1)
            saved = json.loads(content_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["items"][0]["news_id"], "0123456789abcdef")
            self.assertTrue((image_dir / "0123456789abcdef.jpg").exists())

    def test_failed_render_request_keeps_daily_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news_file = root / "news.json"
            content_file = root / "generated_content.json"
            state_file = root / "generation_state.json"
            news_file.write_text(json.dumps({"items": [{
                "id": "0123456789abcdef", "title": "Berita baru", "published": "2026-10-24T00:00:00Z",
            }]}), encoding="utf-8")
            content_file.write_text(json.dumps({"items": []}), encoding="utf-8")
            with mock.patch.dict("os.environ", {
                "GITHUB_TOKEN": "test-github-actions-token",
                "GITHUB_RUN_ID": "12345",
                "GITHUB_RUN_ATTEMPT": "1",
            }), mock.patch.object(request_render_generation, "NEWS_FILE", news_file), \
                 mock.patch.object(request_render_generation, "CONTENT_FILE", content_file), \
                 mock.patch.object(request_render_generation, "STATE_FILE", state_file), \
                 mock.patch.object(request_render_generation, "call_render", side_effect=RuntimeError("simulated")) as render_call:
                with self.assertRaises(RuntimeError):
                    request_render_generation.main()
                request_render_generation.main()
            self.assertEqual(render_call.call_count, 1)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["last_attempt_local_date"], datetime.now(generate_editorial.WIB).date().isoformat())


if __name__ == "__main__":
    unittest.main()
