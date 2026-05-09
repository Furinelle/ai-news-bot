import unittest

from ai_news_bot.llm import build_chat_payload
from ai_news_bot.models import NewsItem


class LlmTests(unittest.TestCase):
    def test_build_chat_payload_includes_fact_safety_rules_and_sources(self):
        payload = build_chat_payload(
            model="summary-model",
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
        self.assertIn("不得编造", joined)
        self.assertIn("翻译或改写为中文", joined)
        self.assertIn("普通新闻不要输出链接", joined)
        self.assertIn("不要使用 Markdown 加粗", joined)
        self.assertIn("https://example.com/chip", joined)
        self.assertIn("科技热点", joined)
        self.assertIn("GitHub Trending", joined)


if __name__ == "__main__":
    unittest.main()
