import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from ai_news_bot.config import load_config
from ai_news_bot.llm import LlmError, summarize_with_llm
from ai_news_bot.main import main


class GrokWeeklyTests(unittest.TestCase):
    def test_grok_config_needs_no_provider_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / "config.json"
            path.write_text('{"llm":{"provider":"grok-build"}}')
            config = load_config(path)
            self.assertEqual(config.llm.provider, "grok-build")
            self.assertEqual(config.llm.api_key, "")

    def test_cli_generation_excludes_publisher_credentials(self):
        report = "# 周报\n2026-W39\n## 🔥 科技热点\n## 🤖 AI动态\n## 📦 GitHub Trending"
        def summarize():
            return summarize_with_llm("", "", "", [], "2026-W39", provider="grok-build")
        with patch.dict(os.environ, {"BLOG_ADMIN_PASSWORD": "private", "XAI_API_KEY": "unused-api-key"}), patch("ai_news_bot.llm.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = report
            self.assertEqual(summarize(), report)
            self.assertNotIn("BLOG_ADMIN_PASSWORD", run.call_args.kwargs["env"])
            self.assertNotIn("XAI_API_KEY", run.call_args.kwargs["env"])
            self.assertIn("--no-subagents", run.call_args.args[0])
            for bad in ["", "402 payment required", "# Wrong date"]:
                run.return_value.stdout = bad
                with self.assertRaises(LlmError):
                    summarize()

    def test_quota_failure_is_not_used_as_report(self):
        with patch("ai_news_bot.llm.subprocess.run") as run:
            run.return_value.returncode = 1
            run.return_value.stderr = "HTTP 402 Payment Required"
            with self.assertRaisesRegex(LlmError, "nothing published"):
                summarize_with_llm("", "", "", [], "2026-W39", provider="grok-build")

    def test_server_gate_and_completed_receipt_skip_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(json.dumps({"llm": {"provider": "grok-build"}, "database_path": str(Path(directory) / "news.sqlite3")}))
            with patch("sys.argv", ["news", "--config", str(config_path), "--send", "--not-before", "2099-01-01"]), patch("ai_news_bot.main.build_report") as build, patch("sys.stdout", io.StringIO()):
                self.assertEqual(main(), 2)
                build.assert_not_called()
            from ai_news_bot.main import default_report_slug
            from zoneinfo import ZoneInfo
            slug = default_report_slug(datetime.now(ZoneInfo("Asia/Shanghai")).date())
            (Path(directory) / f"grok-published-{slug}.json").write_text('{"already_published":true}')
            with patch("sys.argv", ["news", "--config", str(config_path), "--send"]), patch("ai_news_bot.main.build_report") as build, patch("sys.stdout", io.StringIO()):
                self.assertEqual(main(), 0)
                build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
