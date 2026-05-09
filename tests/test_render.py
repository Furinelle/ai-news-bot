import unittest

from ai_news_bot.models import NewsItem
from ai_news_bot.render import render_fallback_report, strip_markdown_emphasis


class RenderTests(unittest.TestCase):
    def test_render_fallback_report_only_keeps_github_trending_links(self):
        report = render_fallback_report(
            [
                NewsItem(
                    title="OpenAI releases a realtime model",
                    url="https://example.com/openai",
                    source="Example",
                    category="AI动态",
                ),
                NewsItem(
                    title="A repository is trending",
                    url="https://github.com/example/repo",
                    source="GitHub Trending",
                    category="GitHub Trending",
                ),
            ],
            date_label="2026年5月9日",
        )

        self.assertIn("📡 Furina · 每日科技/AI日报", report)
        self.assertIn("2026年5月9日", report)
        self.assertIn("二、🤖 AI动态", report)
        self.assertIn("三、📦 GitHub Trending", report)
        self.assertIn("来源：Example", report)
        self.assertNotIn("https://example.com/openai", report)
        self.assertIn("https://github.com/example/repo", report)

    def test_strip_markdown_emphasis_removes_bold_markers(self):
        text = strip_markdown_emphasis("**重点** 和 __项目__")

        self.assertEqual(text, "重点 和 项目")


if __name__ == "__main__":
    unittest.main()
