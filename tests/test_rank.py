import unittest

from ai_news_bot.models import NewsItem
from ai_news_bot.rank import select_report_items, select_report_items_with_fallback


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

    def test_select_report_items_selects_ten_per_section_when_available(self):
        items = []
        for category in ("科技热点", "AI动态", "GitHub Trending"):
            items.extend(
                NewsItem(
                    title=f"{category} {i}",
                    url=f"https://example.com/{category}/{i}",
                    source="Source",
                    category=category,
                    score=i,
                )
                for i in range(17)
            )

        selected = select_report_items(items, limit=45)

        self.assertEqual(len(selected), 45)
        self.assertEqual(sum(1 for item in selected if item.category == "科技热点"), 15)
        self.assertEqual(sum(1 for item in selected if item.category == "AI动态"), 15)
        self.assertEqual(sum(1 for item in selected if item.category == "GitHub Trending"), 15)

    def test_select_report_items_with_fallback_refills_sections(self):
        primary = []
        fallback = []
        for category in ("科技热点", "AI动态"):
            primary.extend(
                NewsItem(
                    title=f"New {category} {i}",
                    url=f"https://example.com/new/{category}/{i}",
                    source="Source",
                    category=category,
                    score=100 + i,
                )
                for i in range(15)
            )
        primary.extend(
            NewsItem(
                title=f"New repo {i}",
                url=f"https://github.com/new/{i}",
                source="GitHub Trending",
                category="GitHub Trending",
                score=100 + i,
            )
            for i in range(3)
        )
        fallback.extend(primary)
        fallback.extend(
            NewsItem(
                title=f"Old repo {i}",
                url=f"https://github.com/old/{i}",
                source="GitHub Trending",
                category="GitHub Trending",
                score=i,
            )
            for i in range(20)
        )

        selected = select_report_items_with_fallback(primary, fallback, limit=45)

        self.assertEqual(len(selected), 45)
        self.assertEqual(sum(1 for item in selected if item.category == "科技热点"), 15)
        self.assertEqual(sum(1 for item in selected if item.category == "AI动态"), 15)
        self.assertEqual(sum(1 for item in selected if item.category == "GitHub Trending"), 15)
        self.assertEqual(sum(1 for item in selected if item.title.startswith("New repo")), 3)
        self.assertEqual(sum(1 for item in selected if item.title.startswith("Old repo")), 12)

    def test_select_report_items_with_fallback_can_keep_github_trending_new_only(self):
        primary = [
            NewsItem(
                title=f"New repo {i}",
                url=f"https://github.com/new/{i}",
                source="GitHub Trending",
                category="GitHub Trending",
                score=100 + i,
            )
            for i in range(3)
        ]
        fallback = [*primary]
        fallback.extend(
            NewsItem(
                title=f"Old repo {i}",
                url=f"https://github.com/old/{i}",
                source="GitHub Trending",
                category="GitHub Trending",
                score=1000 + i,
            )
            for i in range(20)
        )
        fallback.extend(
            NewsItem(
                title=f"Tech fallback {i}",
                url=f"https://example.com/tech/{i}",
                source="RSS",
                category="科技热点",
                score=i,
            )
            for i in range(20)
        )

        selected = select_report_items_with_fallback(
            primary_items=primary,
            fallback_items=fallback,
            limit=18,
            no_fallback_categories={"GitHub Trending"},
        )

        self.assertEqual(sum(1 for item in selected if item.title.startswith("New repo")), 3)
        self.assertEqual(sum(1 for item in selected if item.title.startswith("Old repo")), 0)

    def test_select_report_items_with_fallback_exhausts_primary_before_using_fallback(self):
        primary = [
            NewsItem(
                title=f"Fresh tech {index}",
                url=f"https://example.com/fresh/{index}",
                source="Fresh",
                category="科技热点",
                score=100 - index,
            )
            for index in range(8)
        ]
        fallback = [
            NewsItem(
                title=f"Yesterday AI {index}",
                url=f"https://example.com/yesterday/{index}",
                source="Yesterday",
                category="AI动态",
                score=1000 - index,
            )
            for index in range(8)
        ]

        selected = select_report_items_with_fallback(primary, fallback, limit=10)

        self.assertEqual(sum(item.source == "Fresh" for item in selected), 8)
        self.assertEqual(sum(item.source == "Yesterday" for item in selected), 2)
        self.assertTrue(all(item.source == "Fresh" for item in selected[:8]))


    def test_select_report_items_reserves_interest_section_without_blocking_primary(self):
        items = []
        for category in ("科技热点", "AI动态", "GitHub Trending"):
            items.extend(
                NewsItem(
                    title=f"{category} {i}",
                    url=f"https://example.com/{category}/{i}",
                    source="Source",
                    category=category,
                    score=i,
                )
                for i in range(10)
            )
        items.extend(
            NewsItem(
                title=f"interest/{i}",
                url=f"https://github.com/interest/{i}",
                source="GitHub 兴趣推荐",
                category="你可能感兴趣",
                score=50 + i,
            )
            for i in range(12)
        )

        selected = select_report_items(items, limit=20, interest_limit=5)

        self.assertEqual(sum(1 for item in selected if item.category == "你可能感兴趣"), 5)
        self.assertGreaterEqual(sum(1 for item in selected if item.category == "科技热点"), 1)
        self.assertGreaterEqual(sum(1 for item in selected if item.category == "AI动态"), 1)
        interest_indexes = [index for index, item in enumerate(selected) if item.category == "你可能感兴趣"]
        primary_indexes = [index for index, item in enumerate(selected) if item.category != "你可能感兴趣"]
        self.assertTrue(interest_indexes)
        self.assertTrue(all(i > max(primary_indexes) for i in interest_indexes) or not primary_indexes)



if __name__ == "__main__":
    unittest.main()
