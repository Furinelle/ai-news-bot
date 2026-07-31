import unittest

from ai_news_bot.github_interest import (
    annotate_match_reason,
    build_search_queries,
    collect_interest_repos,
    score_repository,
)
from ai_news_bot.models import INTEREST_CATEGORY, NewsItem
from ai_news_bot.star_profile import StarProfile, build_profile_from_repos


class GitHubInterestTests(unittest.TestCase):
    def test_build_profile_and_queries_use_star_signals(self):
        repos = [
            {
                "full_name": "alice/claude-helper",
                "language": "Python",
                "topics": ["claude-code", "mcp"],
                "description": "Claude Code MCP server for agent memory",
            },
            {
                "full_name": "bob/tg-gate",
                "language": "Rust",
                "topics": ["telegram-bot", "rust"],
                "description": "Telegram bot framework for approval workflows",
            },
        ]
        profile = build_profile_from_repos("Furinelle", repos)

        self.assertIn("alice/claude-helper", profile.starred)
        self.assertTrue(any(lang == "Python" for lang, _ in profile.languages))
        self.assertTrue(any(topic == "claude-code" for topic, _ in profile.topics))

        from datetime import datetime
        from zoneinfo import ZoneInfo

        # 周报汇总整周兴趣簇，应同时覆盖 mcp / telegram / pixiv 等主题
        tuesday = datetime(2026, 7, 28, tzinfo=ZoneInfo("Asia/Shanghai"))
        queries = build_search_queries(profile, max_queries=14, now=tuesday)
        self.assertTrue(queries)
        self.assertTrue(any("mcp" in query for query in queries))
        self.assertTrue(any("telegram" in query or "pixiv" in query for query in queries))
        self.assertTrue(all("fork:false" in query for query in queries))

    def test_score_repository_prefers_distinctive_unstarred_tools(self):
        profile = StarProfile(
            username="Furinelle",
            starred=["someone/already-starred"],
            languages=[("Rust", 5), ("Python", 10)],
            topics=[("telegram-bot", 4), ("claude-code", 6), ("mcp", 3)],
            keywords=[("telegram", 3), ("memory", 2), ("agent", 2)],
        )
        gem = {
            "full_name": "example/tg-approval-daemon",
            "description": "Self-hosted Telegram bot single binary for Claude Code permission approval",
            "language": "Rust",
            "topics": ["telegram-bot", "cli", "self-hosted"],
            "stargazers_count": 420,
            "fork": False,
            "archived": False,
            "html_url": "https://github.com/example/tg-approval-daemon",
        }
        awesome = {
            "full_name": "example/awesome-agents",
            "description": "Awesome curated list of AI agent learning resources and links",
            "language": "Python",
            "topics": ["ai-agents"],
            "stargazers_count": 12000,
            "fork": False,
            "archived": False,
            "html_url": "https://github.com/example/awesome-agents",
        }
        starred = {
            **gem,
            "full_name": "someone/already-starred",
            "html_url": "https://github.com/someone/already-starred",
        }

        gem_score = score_repository(gem, profile)
        awesome_score = score_repository(awesome, profile)
        starred_score = score_repository(starred, profile)

        self.assertGreater(gem_score, 4.0)
        self.assertLess(awesome_score, gem_score)
        self.assertLess(starred_score, 0)

    def test_collect_interest_repos_ranks_and_limits(self):
        profile = StarProfile(
            username="Furinelle",
            starred=["skip/me"],
            languages=[("Rust", 3)],
            topics=[("telegram-bot", 5), ("mcp", 4)],
            keywords=[("telegram", 3), ("mcp", 2)],
        )

        def fake_search(query, token=None, per_page=12, client=None, **_kwargs):
            return [
                {
                    "full_name": "skip/me",
                    "description": "Already starred telegram bot",
                    "language": "Rust",
                    "topics": ["telegram-bot"],
                    "stargazers_count": 500,
                    "html_url": "https://github.com/skip/me",
                },
                {
                    "full_name": "nice/mcp-telegram",
                    "description": "MCP server bridge for Telegram bots with approval workflow",
                    "language": "Rust",
                    "topics": ["mcp", "telegram-bot", "cli"],
                    "stargazers_count": 300,
                    "html_url": "https://github.com/nice/mcp-telegram",
                    "pushed_at": "2026-07-01T00:00:00Z",
                },
                {
                    "full_name": "noise/readme-only",
                    "description": "x",
                    "language": "Python",
                    "topics": [],
                    "stargazers_count": 200,
                    "html_url": "https://github.com/noise/readme-only",
                },
            ]

        items = collect_interest_repos(
            profile,
            limit=5,
            search=fake_search,
            max_queries=3,
        )

        self.assertTrue(items)
        self.assertTrue(all(item.category == INTEREST_CATEGORY for item in items))
        self.assertIn("nice/mcp-telegram", {item.title for item in items})
        self.assertNotIn("skip/me", {item.title for item in items})
        self.assertNotIn("noise/readme-only", {item.title for item in items})

    def test_annotate_match_reason_appends_topics(self):
        profile = StarProfile(
            username="Furinelle",
            topics=[("mcp", 3)],
            languages=[("Rust", 2)],
        )
        item = NewsItem(
            title="a/b",
            url="https://github.com/a/b",
            source="GitHub 兴趣推荐",
            summary="MCP server written in Rust",
            category=INTEREST_CATEGORY,
        )
        annotated = annotate_match_reason(item, profile)
        self.assertIn("匹配：", annotated.summary)
        self.assertIn("topic:mcp", annotated.summary)


if __name__ == "__main__":
    unittest.main()
