import os
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


if __name__ == "__main__":
    unittest.main()
