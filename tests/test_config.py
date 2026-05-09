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
                        },
                        "pushplus": {
                            "token_env": "TEST_PUSHPLUS_TOKEN",
                            "channel": "clawbot",
                            "template": "txt",
                        },
                        "limits": {"max_items": 12},
                    },
                    handle,
                )

            old_env = os.environ.copy()
            try:
                os.environ["TEST_LLM_KEY"] = "llm-secret"
                os.environ["TEST_PUSHPLUS_TOKEN"] = "push-secret"

                config = load_config(config_path)

                self.assertEqual(config.llm.api_key, "llm-secret")
                self.assertEqual(config.llm.model, "news-model")
                self.assertEqual(config.pushplus.token, "push-secret")
                self.assertEqual(config.pushplus.channel, "clawbot")
                self.assertEqual(config.limits.max_items, 12)
            finally:
                os.environ.clear()
                os.environ.update(old_env)


if __name__ == "__main__":
    unittest.main()

