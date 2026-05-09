import unittest

from ai_news_bot.models import NewsItem
from ai_news_bot.rank import select_report_items


class RankTests(unittest.TestCase):
    def test_select_report_items_balances_primary_sections_before_global_fill(self):
        items = [
            NewsItem(title=f"Repo {i}", url=f"https://github.com/x/{i}", source="GitHub", category="GitHub Trending", score=1000)
            for i in range(8)
        ]
        items.extend(
            [
                NewsItem(title="AI story", url="https://example.com/ai", source="RSS", category="AI动态", score=1),
                NewsItem(title="Tech story", url="https://example.com/tech", source="RSS", category="科技热点", score=1),
            ]
        )

        selected = select_report_items(items, limit=6)

        self.assertIn("AI动态", {item.category for item in selected})
        self.assertIn("科技热点", {item.category for item in selected})
        self.assertLessEqual(
            sum(1 for item in selected if item.category == "GitHub Trending"),
            4,
        )


if __name__ == "__main__":
    unittest.main()

