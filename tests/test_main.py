import json
import os
import sys
import tempfile
import unittest
from datetime import date

from ai_news_bot import main as main_module
from ai_news_bot.main import (
    build_push_body,
    build_report,
    summarize_remote_push_result,
    summarize_upload_results,
    write_html_report_files,
)
from ai_news_bot.models import NewsItem
from ai_news_bot.r2 import R2UploadResult
from ai_news_bot.storage import NewsStore


class MainTests(unittest.TestCase):
    def test_remote_push_body_contains_blog_link(self):
        body = build_push_body("2026年7月12日–7月18日", 45, "https://blog.example.com/feed/weekly-news-2026-W29")

        self.assertIn("周报已发布到博客", body)
        self.assertIn("https://blog.example.com/feed/weekly-news-2026-W29", body)

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
            main_module.fetch_hacker_news = lambda limit=20, min_score=40, **_k: [
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

    def test_collect_items_skips_sources_that_fail(self):
        sources = {
            "rss": [
                {"name": "Broken RSS", "url": "https://example.com/broken", "category": "AI动态"},
                {"name": "Good RSS", "url": "https://example.com/good", "category": "AI动态"},
            ],
            "json_apis": [{"name": "Broken API", "url": "https://example.com/api", "category": "科技热点"}],
            "hacker_news": {"enabled": True, "limit": 1},
            "github_trending": {"enabled": True, "since": "daily", "limit": 1, "languages": [""]},
        }
        original_rss = main_module.fetch_rss_feed
        original_json = main_module.fetch_json_api
        original_hn = main_module.fetch_hacker_news
        original_github = main_module.fetch_github_trending
        try:
            def fake_rss(url, source, category):
                if source == "Broken RSS":
                    raise RuntimeError("429 Too Many Requests")
                return [NewsItem(title="Good AI", url="https://example.com/good", source=source, category=category)]

            main_module.fetch_rss_feed = fake_rss
            main_module.fetch_json_api = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("429 Too Many Requests"))
            main_module.fetch_hacker_news = lambda limit=20, min_score=40, **_k: (_ for _ in ()).throw(RuntimeError("429 Too Many Requests"))
            main_module.fetch_github_trending = lambda **_kwargs: [
                NewsItem(
                    title="Repo",
                    url="https://github.com/example/repo",
                    source="GitHub Trending",
                    category="GitHub Trending",
                )
            ]

            items = main_module.collect_items(sources, max_items=10)

            self.assertIn("Good AI", {item.title for item in items})
            self.assertIn("Repo", {item.title for item in items})
        finally:
            main_module.fetch_rss_feed = original_rss
            main_module.fetch_json_api = original_json
            main_module.fetch_hacker_news = original_hn
            main_module.fetch_github_trending = original_github

    def test_collect_items_expands_github_trending_candidates_across_time_windows(self):
        sources = {
            "hacker_news": {"enabled": False},
            "github_trending": {
                "enabled": True,
                "since": "weekly",
                "extra_since": ["monthly"],
                "limit": 40,
                "languages": [""],
            },
        }
        calls = []
        original_github = main_module.fetch_github_trending
        try:
            def fake_github(language, since, limit, **_k):
                calls.append((language, since, limit))
                offset = {"weekly": 0, "monthly": 20}[since]
                return [
                    NewsItem(
                        title=f"Repo {offset + index}",
                        url=f"https://github.com/example/{offset + index}",
                        source="GitHub Trending",
                        category="GitHub Trending",
                        score=1000 - index,
                    )
                    for index in range(20)
                ]

            main_module.fetch_github_trending = fake_github

            items = main_module.collect_items(sources, max_items=150)

            github_items = [item for item in items if item.category == "GitHub Trending"]
            self.assertEqual(len(github_items), 40)
            self.assertEqual([call[1] for call in calls], ["weekly", "monthly"])
            self.assertTrue(all(call[2] == 25 for call in calls))  # per-request cap
        finally:
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
                main_module.collect_items = lambda _sources, max_items, **_k: [
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

    def test_build_report_prefers_latest_day_then_week_window_unsent_candidates(self):
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
                        "limits": {"max_items": 10, "max_report_items": 3},
                        "database_path": database_path,
                    },
                    handle,
                )
            with open(sources_path, "w", encoding="utf-8") as handle:
                json.dump({}, handle)

            midweek_unsent = NewsItem(
                title="Midweek unsent",
                url="https://example.com/midweek-unsent",
                source="Midweek",
                category="AI动态",
            )
            midweek_sent = NewsItem(
                title="Midweek already sent",
                url="https://example.com/midweek-sent",
                source="Midweek",
                category="AI动态",
            )
            outside_window = NewsItem(
                title="Outside window",
                url="https://example.com/outside-window",
                source="Old",
                category="AI动态",
            )
            week_end_fresh = NewsItem(
                title="Week end fresh",
                url="https://example.com/week-end-fresh",
                source="Today",
                category="科技热点",
            )
            with NewsStore(database_path) as store:
                # report_date=2026-07-13 的 7 天窗口是 07-07..07-13；07-05 在窗外
                store.remember_candidates([outside_window], discovered_on="2026-07-05")
                store.remember_candidates(
                    [midweek_unsent, midweek_sent],
                    discovered_on="2026-07-10",
                )
                store.mark_seen([midweek_sent])

            old_env = os.environ.copy()
            original_collect = main_module.collect_items
            try:
                os.environ["TEST_LLM_KEY"] = "llm-secret"
                main_module.collect_items = lambda _sources, max_items, **_k: [week_end_fresh]

                _report, selected = build_report(
                    config_path,
                    sources_path,
                    use_llm=False,
                    mark_seen=False,
                    persist_candidates=True,
                    report_date=date(2026, 7, 13),
                )

                titles = [item.title for item in selected]
                self.assertIn("Week end fresh", titles)
                self.assertIn("Midweek unsent", titles)
                self.assertNotIn("Midweek already sent", titles)
                self.assertNotIn("Outside window", titles)
            finally:
                main_module.collect_items = original_collect
                os.environ.clear()
                os.environ.update(old_env)

    def test_dry_run_does_not_write_default_report_files(self):
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
                        "report": {"output_dir": os.path.join(tmp, "reports")},
                        "limits": {"max_items": 10, "max_report_items": 5},
                        "database_path": database_path,
                    },
                    handle,
                )
            with open(sources_path, "w", encoding="utf-8") as handle:
                json.dump({}, handle)

            old_env = os.environ.copy()
            old_argv = sys.argv[:]
            original_collect = main_module.collect_items
            try:
                os.environ["TEST_LLM_KEY"] = "llm-secret"
                main_module.collect_items = lambda _sources, max_items, **_k: [
                    NewsItem(title="Test AI news", url="https://example.com/ai", source="Example")
                ]
                sys.argv = [
                    "ai-news-bot",
                    "--config",
                    config_path,
                    "--sources",
                    sources_path,
                    "--dry-run",
                    "--no-llm",
                ]

                self.assertEqual(main_module.main(), 0)
                self.assertFalse(os.path.exists(os.path.join(tmp, "reports")))
            finally:
                main_module.collect_items = original_collect
                sys.argv = old_argv
                os.environ.clear()
                os.environ.update(old_env)

    def test_write_html_report_files_creates_mobile_reading_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path, latest_path = write_html_report_files(
                "# 标题\n2026年6月26日\n\n## AI动态\n\n1. [Repo](https://github.com/example/repo) **发布**。",
                tmp,
                "2026-06-26",
            )

            html = report_path.read_text(encoding="utf-8")

        self.assertEqual(report_path.name, "2026-06-26.html")
        self.assertEqual(latest_path.name, "latest.html")
        self.assertIn('<meta name="viewport"', html)
        self.assertIn('<a href="https://github.com/example/repo"', html)
        self.assertIn("<strong>发布</strong>", html)

    def test_summarize_remote_push_result_drops_device_tokens(self):
        summary = summarize_remote_push_result(
            {
                "ok": True,
                "message": "sent",
                "timestamp": "now",
                "data": {
                    "push_id": "push-1",
                    "target_devices": 1,
                    "daily_limit": 1000,
                    "remaining": 999,
                    "results": [{"deviceToken": "secret-device-token"}],
                },
            }
        )

        self.assertEqual(summary["push_id"], "push-1")
        self.assertEqual(summary["target_devices"], 1)
        self.assertNotIn("results", summary)
        self.assertNotIn("secret-device-token", repr(summary))

    def test_summarize_upload_results_drops_signed_urls(self):
        summary = summarize_upload_results(
            [R2UploadResult(bucket="furina-ai-news", key="daily/report.html", url="https://signed.example.com")]
        )

        self.assertEqual(summary, [{"bucket": "furina-ai-news", "key": "daily/report.html", "has_url": True}])
        self.assertNotIn("signed.example.com", repr(summary))


if __name__ == "__main__":
    unittest.main()
