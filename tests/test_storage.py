import os
import sqlite3
import tempfile
import unittest

from ai_news_bot.models import NewsItem
from ai_news_bot.storage import NewsStore


class StorageTests(unittest.TestCase):
    def test_clear_seen_removes_seen_url_cache_and_returns_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = os.path.join(tmp, "history.sqlite3")
            item = NewsItem(title="Cached news", url="https://example.com/news", source="Example")

            with NewsStore(database_path) as store:
                store.mark_seen([item])
                self.assertEqual(store.filter_new([item]), [])

                removed = store.clear_seen()

                self.assertEqual(removed, 1)
                self.assertEqual(store.filter_new([item]), [item])

    def test_telegram_github_sent_cache_is_scoped_by_chat_and_normalizes_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = os.path.join(tmp, "history.sqlite3")

            with NewsStore(database_path) as store:
                store.mark_telegram_github_sent(
                    [("https://github.com/Owner/Repo?utm_source=test", "Owner/Repo")],
                    "@FurinadeHub",
                )

                self.assertEqual(
                    store.filter_unsent_telegram_github(["https://github.com/owner/repo"], "@FurinadeHub"),
                    [],
                )
                self.assertEqual(
                    store.filter_unsent_telegram_github(["https://github.com/owner/repo"], "@OtherChannel"),
                    ["https://github.com/owner/repo"],
                )

    def test_seen_cache_backfills_legacy_github_url_casing(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = os.path.join(tmp, "history.sqlite3")
            with NewsStore(database_path):
                pass
            connection = sqlite3.connect(database_path)
            connection.execute(
                "INSERT INTO seen_urls (url, title, source) VALUES (?, ?, ?)",
                ("https://github.com/Owner/Repo", "Owner/Repo", "GitHub Trending"),
            )
            connection.commit()
            connection.close()

            with NewsStore(database_path) as store:
                item = NewsItem(
                    title="Owner/Repo",
                    url="https://github.com/owner/repo",
                    source="GitHub Trending",
                    category="GitHub Trending",
                )

                self.assertEqual(store.filter_new([item]), [])

    def test_candidates_preserve_first_discovery_day_and_restore_yesterdays_unsent_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = os.path.join(tmp, "history.sqlite3")
            yesterday = NewsItem(
                title="Yesterday story",
                url="https://example.com/yesterday",
                source="Example",
                summary="Original summary",
                category="AI动态",
                published_at="2026-07-12T08:00:00Z",
                score=7,
                tags=["ai"],
            )
            refreshed = NewsItem(
                title="Yesterday story updated",
                url="https://example.com/yesterday",
                source="Example",
                summary="Updated summary",
                category="AI动态",
                published_at="2026-07-12T08:00:00Z",
                score=9,
                tags=["ai", "update"],
            )

            with NewsStore(database_path) as store:
                store.remember_candidates([yesterday], discovered_on="2026-07-12")
                store.remember_candidates([refreshed], discovered_on="2026-07-13")

                restored = store.candidates_discovered_on("2026-07-12")

            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0].title, "Yesterday story updated")
            self.assertEqual(restored[0].summary, "Updated summary")
            self.assertEqual(restored[0].score, 9)
            self.assertEqual(restored[0].tags, ["ai", "update"])

    def test_filter_new_rejects_a_cross_source_version_of_an_already_sent_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = os.path.join(tmp, "history.sqlite3")
            sent = NewsItem(
                title="Apple sues OpenAI over alleged trade secret theft",
                url="https://techcrunch.example/apple-openai-lawsuit",
                source="TechCrunch AI",
            )
            duplicate = NewsItem(
                title="Apple sues OpenAI for allegedly stealing hardware secrets",
                url="https://verge.example/apple-openai-secrets",
                source="The Verge AI",
            )

            with NewsStore(database_path) as store:
                store.mark_seen([sent])

                self.assertEqual(store.filter_new([duplicate]), [])


if __name__ == "__main__":
    unittest.main()
