import unittest

from ai_news_bot.blog import BlogPublishError, publish_report_to_blog


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data
        self.text = text

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


class BlogPublishTests(unittest.TestCase):
    def test_publish_logs_in_and_creates_public_daily_post(self):
        client = FakeClient(
            [
                FakeResponse(data={"success": True, "token": "jwt-token"}),
                FakeResponse(data={"insertedId": 42}),
            ]
        )

        result = publish_report_to_blog(
            base_url="https://blog.example.com/",
            username="furina",
            password="secret",
            report="# 每日新闻\n\n正文",
            slug="2026-07-18",
            selected_count=45,
            client=client,
        )

        self.assertEqual(result.feed_id, 42)
        self.assertEqual(result.alias, "daily-news-2026-07-18")
        self.assertEqual(result.url, "https://blog.example.com/feed/daily-news-2026-07-18")
        self.assertTrue(result.created)
        self.assertEqual(client.calls[0][1], "https://blog.example.com/api/auth/login")
        create_call = client.calls[1]
        self.assertEqual(create_call[1], "https://blog.example.com/api/feed")
        self.assertEqual(create_call[2]["headers"]["Authorization"], "Bearer jwt-token")
        self.assertEqual(create_call[2]["json"]["title"], "每日科技 / AI 日报 · 2026-07-18")
        self.assertEqual(create_call[2]["json"]["alias"], "daily-news-2026-07-18")
        self.assertEqual(create_call[2]["json"]["content"], "# 每日新闻\n\n正文")
        self.assertEqual(create_call[2]["json"]["tags"], ["每日新闻", "AI", "科技"])
        self.assertFalse(create_call[2]["json"]["draft"])
        self.assertTrue(create_call[2]["json"]["listed"])

    def test_existing_daily_post_is_idempotent(self):
        client = FakeClient(
            [
                FakeResponse(data={"success": True, "token": "jwt-token"}),
                FakeResponse(status_code=400, text="Content already exists"),
                FakeResponse(data={"id": 12, "alias": "daily-news-2026-07-18"}),
            ]
        )

        result = publish_report_to_blog(
            base_url="https://blog.example.com",
            username="furina",
            password="secret",
            report="same report",
            slug="2026-07-18",
            selected_count=45,
            client=client,
        )

        self.assertEqual(result.feed_id, 12)
        self.assertFalse(result.created)
        self.assertEqual(client.calls[2][0:2], ("GET", "https://blog.example.com/api/feed/daily-news-2026-07-18"))

    def test_login_failure_does_not_attempt_publish(self):
        client = FakeClient([FakeResponse(status_code=403, text="Invalid credentials")])

        with self.assertRaisesRegex(BlogPublishError, "login failed"):
            publish_report_to_blog(
                base_url="https://blog.example.com",
                username="furina",
                password="bad",
                report="report",
                slug="2026-07-18",
                selected_count=1,
                client=client,
            )

        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
