import json
import os
import tempfile
import unittest

from ai_news_bot import main as main_module
from ai_news_bot.main import build_report
from ai_news_bot.models import NewsItem
from ai_news_bot.storage import NewsStore


class MainTests(unittest.TestCase):
    def test_collect_items_balances_categories_when_applying_max_items(self):
        sources = {
            "rss": [{"name": "AI RSS", "url": "https://example.com/rss", "category": "AI动态"}],
            "hacker_news": {"enabled": True, "limit": 1},
            "github_trending": {"enabled": True, "since": "daily", "limit": 8, "languages": [""]},
        }
        original_rss = main_module.fetch_rss_feed
        original_hn = main_module.fetch_hacker_news
        original_github = main_module.fetch_github_trending
        try:
            main_module.fetch_rss_feed = lambda **_kwargs: [
                NewsItem(title="AI story", url="https://example.com/ai", source="AI RSS", category="AI动态", score=1)
            ]
            main_module.fetch_hacker_news = lambda limit: [
                NewsItem(title="Tech story", url="https://example.com/tech", source="HN", category="科技热点", score=1)
            ]
            main_module.fetch_github_trending = lambda **_kwargs: [
                NewsItem(
                    title=f"Repo {index}",
                    url=f"https://github.com/example/{index}",
                    source="GitHub",
                    category="GitHub Trending",
                    score=1000,
                )
                for index in range(8)
            ]

            items = main_module.collect_items(sources, max_items=6)

            self.assertIn("AI动态", {item.category for item in items})
            self.assertIn("科技热点", {item.category for item in items})
        finally:
            main_module.fetch_rss_feed = original_rss
            main_module.fetch_hacker_news = original_hn
            main_module.fetch_github_trending = original_github

    def test_build_report_can_skip_marking_items_seen_for_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "config.json")
            sources_path = os.path.join(tmp, "sources.json")
            database_path = os.path.join(tmp, "history.sqlite3")
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "llm": {
                            "base_url": "https://api.example.com/v1",
                            "api_key_env": "TEST_LLM_KEY",
                            "model": "summary-model",
                        },
                        "pushplus": {"token_env": "TEST_PUSHPLUS_TOKEN"},
                        "limits": {"max_items": 10, "max_report_items": 5},
                        "database_path": database_path,
                    },
                    handle,
                )
            with open(sources_path, "w", encoding="utf-8") as handle:
                json.dump({}, handle)

            old_env = os.environ.copy()
            original_collect = main_module.collect_items
            try:
                os.environ["TEST_LLM_KEY"] = "llm-secret"
                os.environ["TEST_PUSHPLUS_TOKEN"] = "push-secret"
                main_module.collect_items = lambda _sources, max_items: [
                    NewsItem(title="Test AI news", url="https://example.com/ai", source="Example")
                ]

                build_report(config_path, sources_path, use_llm=False, mark_seen=False)

                with NewsStore(database_path) as store:
                    fresh = store.filter_new(
                        [NewsItem(title="Test AI news", url="https://example.com/ai", source="Example")]
                    )
                self.assertEqual(len(fresh), 1)
            finally:
                main_module.collect_items = original_collect
                os.environ.clear()
                os.environ.update(old_env)


if __name__ == "__main__":
    unittest.main()
