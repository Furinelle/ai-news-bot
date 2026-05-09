import unittest

from ai_news_bot.models import NewsItem
from ai_news_bot.render import render_fallback_report


class RenderTests(unittest.TestCase):
    def test_render_fallback_report_preserves_source_links(self):
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
        self.assertIn("https://example.com/openai", report)
        self.assertIn("https://github.com/example/repo", report)
        self.assertIn("AI动态", report)


if __name__ == "__main__":
    unittest.main()
