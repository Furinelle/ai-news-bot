import unittest

from ai_news_bot.fetch_rss import clean_summary


class FetchRssTests(unittest.TestCase):
    def test_clean_summary_strips_html_and_unescapes_entities(self):
        summary = clean_summary("A&nbsp;<b>new</b>&#160;AI tool [&#8230;]")

        self.assertEqual(summary, "A new AI tool [...]")


if __name__ == "__main__":
    unittest.main()

