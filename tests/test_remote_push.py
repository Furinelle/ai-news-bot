import unittest

from ai_news_bot.remote_push import build_remote_push_payload, send_remote_push


class FakeResponse:
    def __init__(self, data=None):
        self.data = data or {"ok": True}

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class RemotePushTests(unittest.TestCase):
    def test_build_remote_push_payload_includes_action_when_present(self):
        payload = build_remote_push_payload(
            title="日报",
            body="已生成",
            action="https://example.com/daily.md",
        )

        self.assertEqual(payload["title"], "日报")
        self.assertEqual(payload["body"], "已生成")
        self.assertEqual(payload["action"], "https://example.com/daily.md")
        self.assertEqual(payload["icon"], "newspaper.fill")

    def test_send_remote_push_uses_bearer_token(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({"pushed": True})

        result = send_remote_push(
            api_key="secret",
            endpoint="https://push.example/push",
            title="日报",
            body="正文",
            post=fake_post,
        )

        self.assertEqual(result, {"pushed": True})
        self.assertEqual(calls[0][0], "https://push.example/push")
        self.assertEqual(calls[0][1]["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(calls[0][1]["json"]["title"], "日报")


if __name__ == "__main__":
    unittest.main()
