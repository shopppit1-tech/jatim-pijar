import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.fetch_news as fetch_news
from scripts.fetch_news import editorial_headline, make_post, stable_id


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


if __name__ == "__main__":
    unittest.main()
