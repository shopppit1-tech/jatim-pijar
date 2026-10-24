import base64
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import scripts.fetch_news as fetch_news
import scripts.generate_editorial as generate_editorial
from scripts.fetch_news import editorial_headline, make_post, stable_id
from scripts.generate_editorial import attempted_today, extract_image, extract_text, newest_unprocessed, parse_json_object


class FetchNewsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
