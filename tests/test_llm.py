import unittest

from ai_news_bot.llm import LlmError, build_chat_payload, summarize_with_llm
from ai_news_bot.models import NewsItem


class LlmTests(unittest.TestCase):
    def test_build_chat_payload_includes_fact_safety_rules_and_sources(self):
        payload = build_chat_payload(
            model="summary-model",
            date_label="2026年5月9日",
            items=[
                NewsItem(
                    title="A chip startup tapes out a new AI chip",
                    url="https://example.com/chip",
                    source="Example",
                    summary="The company says it completed tape-out.",
                    category="AI动态",
                )
            ],
        )

        joined = "\n".join(message["content"] for message in payload["messages"])

        self.assertEqual(payload["model"], "summary-model")
        self.assertIn("2026年5月9日", joined)
        self.assertIn("必须原样使用这个日期", joined)
        self.assertIn("不得编造", joined)
        self.assertIn("翻译或改写为中文", joined)
        self.assertIn("发生了什么", joined)
        self.assertIn("为什么值得看", joined)
        self.assertIn("120到180个中文字符", joined)
        self.assertIn("每节内部必须使用 1. 2. 3. 编号", joined)
        self.assertIn("## 🔥 科技热点", joined)
        self.assertIn("## 🤖 AI动态", joined)
        self.assertIn("## 📦 GitHub Trending", joined)
        self.assertIn("普通新闻不要输出链接", joined)
        self.assertIn("Markdown 一级标题", joined)
        self.assertIn("https://example.com/chip", joined)
        self.assertIn("科技热点", joined)
        self.assertIn("GitHub Trending", joined)

    def test_summarize_with_llm_uses_configurable_timeout_and_wraps_timeout_errors(self):
        calls = []

        def post(_url, **kwargs):
            calls.append(kwargs)
            raise TimeoutError("slow provider")

        with self.assertRaisesRegex(LlmError, "LLM request timed out"):
            summarize_with_llm(
                base_url="https://api.example.com",
                api_key="secret",
                model="summary-model",
                items=[],
                date_label="2026年5月9日",
                timeout_seconds=240,
                post=post,
            )

        self.assertEqual(calls[0]["timeout"], 240)


if __name__ == "__main__":
    unittest.main()
