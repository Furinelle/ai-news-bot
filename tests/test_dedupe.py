import unittest

from ai_news_bot.dedupe import dedupe_items
from ai_news_bot.models import NewsItem


class DedupeTests(unittest.TestCase):
    def test_dedupe_items_keeps_first_item_for_same_url_or_title(self):
        items = [
            NewsItem(title="OpenAI releases a realtime model", url="https://a.example/news", source="A"),
            NewsItem(title="OpenAI releases a realtime model", url="https://b.example/news", source="B"),
            NewsItem(title="Different title", url="https://a.example/news", source="C"),
            NewsItem(title="Anthropic ships finance agents", url="https://c.example/news", source="C"),
        ]

        result = dedupe_items(items)

        self.assertEqual([item.source for item in result], ["A", "C"])


if __name__ == "__main__":
    unittest.main()

