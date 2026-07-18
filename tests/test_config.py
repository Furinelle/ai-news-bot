import json
import os
import tempfile
import unittest

from ai_news_bot.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_resolves_llm_and_pushplus_from_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "config.json")
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "llm": {
                            "base_url": "https://api.example.com/v1",
                            "api_key_env": "TEST_LLM_KEY",
                            "model": "news-model",
                            "timeout_seconds": 240,
                        },
                        "pushplus": {
                            "token_env": "TEST_PUSHPLUS_TOKEN",
                            "channel": "clawbot",
                            "template": "markdown",
                        },
                        "telegram": {
                            "enabled": True,
                            "bot_token_env": "TEST_TELEGRAM_BOT_TOKEN",
                            "chat_id": "@FurinadeHub",
                        },
                        "blog": {
                            "enabled": True,
                            "base_url": "https://blog.example.com/",
                            "username_env": "TEST_BLOG_USERNAME",
                            "password_env": "TEST_BLOG_PASSWORD",
                            "title_prefix": "每日新闻",
                            "tags": ["日报", "AI"],
                        },
                        "limits": {"max_items": 12},
                    },
                    handle,
                )

            old_env = os.environ.copy()
            try:
                os.environ["TEST_LLM_KEY"] = "llm-secret"
                os.environ["TEST_PUSHPLUS_TOKEN"] = "push-secret"
                os.environ["TEST_TELEGRAM_BOT_TOKEN"] = "telegram-secret"
                os.environ["TEST_BLOG_USERNAME"] = "furina"
                os.environ["TEST_BLOG_PASSWORD"] = "blog-secret"

                config = load_config(config_path)

                self.assertEqual(config.llm.api_key, "llm-secret")
                self.assertEqual(config.llm.model, "news-model")
                self.assertEqual(config.llm.timeout_seconds, 240)
                self.assertEqual(config.pushplus.token, "push-secret")
                self.assertEqual(config.pushplus.channel, "clawbot")
                self.assertTrue(config.telegram.enabled)
                self.assertEqual(config.telegram.bot_token, "telegram-secret")
                self.assertEqual(config.telegram.chat_id, "@FurinadeHub")
                self.assertTrue(config.blog.enabled)
                self.assertEqual(config.blog.base_url, "https://blog.example.com")
                self.assertEqual(config.blog.username, "furina")
                self.assertEqual(config.blog.password, "blog-secret")
                self.assertEqual(config.blog.title_prefix, "每日新闻")
                self.assertEqual(config.blog.tags, ("日报", "AI"))
                self.assertEqual(config.limits.max_items, 12)
                self.assertEqual(config.limits.max_report_items, 45)
            finally:
                os.environ.clear()
                os.environ.update(old_env)


if __name__ == "__main__":
    unittest.main()
