import unittest

from ai_news_bot.pushplus import build_pushplus_payload


class PushplusTests(unittest.TestCase):
    def test_build_pushplus_payload_targets_clawbot_text_template(self):
        payload = build_pushplus_payload(
            token="secret",
            title="科技与AI日报",
            content="日报正文",
            channel="clawbot",
            template="txt",
        )

        self.assertEqual(
            payload,
            {
                "token": "secret",
                "title": "科技与AI日报",
                "content": "日报正文",
                "channel": "clawbot",
                "template": "txt",
            },
        )


if __name__ == "__main__":
    unittest.main()

