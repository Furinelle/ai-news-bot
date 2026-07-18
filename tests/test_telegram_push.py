import unittest

from ai_news_bot.telegram_push import (
    TelegramPushError,
    build_telegram_github_message,
    build_telegram_payload,
    extract_github_trending_messages,
    send_telegram_messages,
)


class FakeResponse:
    def __init__(self, data=None, status_code=200, http_error=None):
        self.data = data or {"ok": True}
        self.status_code = status_code
        self.http_error = http_error

    def raise_for_status(self):
        if self.http_error:
            raise self.http_error
        return None

    def json(self):
        return self.data


class TelegramPushTests(unittest.TestCase):
    def test_extract_github_trending_messages_from_report_section(self):
        report = """# 日报

## 🤖 AI动态

1. 普通新闻（来源：[Example](https://example.com)）

## 📦 GitHub Trending

1. [owner/repo](https://github.com/owner/repo) — 一个中文简介。
2. [owner/repo](https://github.com/owner/repo?utm_source=test) — 重复仓库。
3. [bad](https://example.com/bad) — 不是 GitHub。

## 🔥 科技热点

1. 另一条新闻
"""

        messages = extract_github_trending_messages(report)

        self.assertEqual(messages, ['<a href="https://github.com/owner/repo">owner/repo</a> — 一个中文简介。'])

    def test_build_telegram_github_message_escapes_html(self):
        message = build_telegram_github_message(
            "[owner/repo](https://github.com/owner/repo) — 支持 <AI> & 工具链。"
        )

        self.assertEqual(
            message,
            '<a href="https://github.com/owner/repo">owner/repo</a> — 支持 &lt;AI&gt; &amp; 工具链。',
        )

    def test_build_telegram_payload_uses_html_and_allows_preview(self):
        payload = build_telegram_payload(chat_id="@FurinadeHub", text="<a href=\"https://github.com/a/b\">a/b</a>")

        self.assertEqual(payload["chat_id"], "@FurinadeHub")
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertFalse(payload["disable_web_page_preview"])

    def test_send_telegram_messages_posts_each_project_as_one_message(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({"ok": True})

        result = send_telegram_messages(
            bot_token="secret-token",
            chat_id="@FurinadeHub",
            messages=["message 1", "message 2"],
            endpoint_base="https://api.telegram.example",
            post=fake_post,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.sent, 2)
        self.assertEqual(calls[0][0], "https://api.telegram.example/botsecret-token/sendMessage")
        self.assertEqual(calls[0][1]["json"]["chat_id"], "@FurinadeHub")
        self.assertEqual(calls[0][1]["json"]["text"], "message 1")
        self.assertEqual(calls[1][1]["json"]["text"], "message 2")

    def test_send_telegram_messages_sanitizes_http_errors(self):
        def fake_post(_url, **_kwargs):
            return FakeResponse({"ok": False, "description": "chat not found"}, status_code=400, http_error=RuntimeError("raw url"))

        with self.assertRaises(TelegramPushError) as ctx:
            send_telegram_messages(
                bot_token="secret-token",
                chat_id="@FurinadeHub",
                messages=["message"],
                endpoint_base="https://api.telegram.example",
                post=fake_post,
            )

        self.assertIn("Telegram API HTTP 400: chat not found", str(ctx.exception))
        self.assertNotIn("secret-token", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
