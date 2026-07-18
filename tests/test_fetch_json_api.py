import json
import unittest
from unittest.mock import patch

from ai_news_bot.fetch_json_api import fetch_json_api


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, *_args):
        return self.data


class JsonApiTests(unittest.TestCase):
    def test_fetch_json_api_maps_spaceflight_news_shape(self):
        payload = {
            "results": [
                {
                    "title": "Rocket Lab wins NASA award",
                    "url": "https://example.com/rocket",
                    "summary": "<p>NASA selected Rocket Lab.</p>",
                    "news_site": "SpaceNews",
                    "published_at": "2026-06-26T00:00:00Z",
                }
            ]
        }

        with patch("ai_news_bot.fetch_json_api.urlopen", return_value=FakeResponse(payload)) as urlopen_mock:
            items = fetch_json_api(
                url="https://api.example.com/articles",
                source="Spaceflight News",
                category="科技热点",
            )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Rocket Lab wins NASA award")
        self.assertEqual(items[0].url, "https://example.com/rocket")
        self.assertEqual(items[0].summary, "NASA selected Rocket Lab.")
        self.assertEqual(items[0].source, "SpaceNews")
        self.assertEqual(items[0].category, "科技热点")
        self.assertIn("User-agent", dict(urlopen_mock.call_args.args[0].header_items()))


if __name__ == "__main__":
    unittest.main()
