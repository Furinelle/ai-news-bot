import unittest

from ai_news_bot.help import build_news_help


class HelpTests(unittest.TestCase):
    def test_build_news_help_lists_available_commands(self):
        help_text = build_news_help()

        for command in (
            "/news",
            "/news_help",
            "/newsid",
            "/news_subscribe 08:30",
            "/news_unsubscribe",
            "/news_schedule",
        ):
            self.assertIn(command, help_text)
        self.assertIn("AI News Bot 指令", help_text)


if __name__ == "__main__":
    unittest.main()
