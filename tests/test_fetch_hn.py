import unittest

import httpx

from ai_news_bot import fetch_hn as fetch_hn_module


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url):
        if url.endswith("topstories.json"):
            return FakeResponse([1, 2, 3])
        if url.endswith("/1.json"):
            return FakeResponse(
                {
                    "title": "New Claude Code release",
                    "url": "https://example.com/ai",
                    "score": 120,
                    "type": "story",
                }
            )
        if url.endswith("/2.json"):
            return FakeResponse(
                {
                    "title": "Random low score",
                    "url": "https://example.com/low",
                    "score": 5,
                    "type": "story",
                }
            )
        if url.endswith("/3.json"):
            return FakeResponse(
                {
                    "title": "Go GC deep dive",
                    "url": "https://example.com/go",
                    "score": 90,
                    "type": "story",
                }
            )
        raise AssertionError(url)


class FetchHnTests(unittest.TestCase):
    def test_fetch_hacker_news_filters_score_and_routes_ai(self):
        original = httpx.Client
        httpx.Client = FakeClient
        try:
            items = fetch_hn_module.fetch_hacker_news(limit=10, min_score=40, fetch_pool=10)
        finally:
            httpx.Client = original

        self.assertEqual(len(items), 2)
        by_title = {item.title: item for item in items}
        self.assertEqual(by_title["New Claude Code release"].category, "AI动态")
        self.assertEqual(by_title["Go GC deep dive"].category, "科技热点")
        self.assertNotIn("Random low score", by_title)


if __name__ == "__main__":
    unittest.main()
