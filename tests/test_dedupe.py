import unittest

from ai_news_bot.dedupe import dedupe_items, same_event
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

    def test_dedupe_items_merges_cross_source_reports_of_the_same_event(self):
        items = [
            NewsItem(
                title="Apple sues OpenAI over alleged trade secret theft",
                url="https://techcrunch.example/apple-openai-lawsuit",
                source="TechCrunch AI",
            ),
            NewsItem(
                title="Apple sues OpenAI for allegedly stealing hardware secrets",
                url="https://verge.example/apple-openai-secrets",
                source="The Verge AI",
            ),
        ]

        result = dedupe_items(items)

        self.assertEqual(result, [items[0]])
        self.assertTrue(same_event(items[0].title, items[1].title))

    def test_same_event_keeps_related_but_distinct_openai_stories(self):
        self.assertFalse(
            same_event(
                "OpenAI launches its new family of models with GPT-5.6",
                "OpenAI says GPT-5.6 is the preferred model for Microsoft Copilot 365",
            )
        )

    def test_same_event_respects_conflicting_months_or_model_versions(self):
        self.assertFalse(
            same_event(
                "The latest AI news we announced in June 2026",
                "The latest AI news we announced in May 2026",
            )
        )
        self.assertFalse(
            same_event(
                "OpenAI launches GPT-5.5",
                "OpenAI launches GPT-5.6",
            )
        )


if __name__ == "__main__":
    unittest.main()
