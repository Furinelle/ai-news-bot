import io
import json
import os
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ai_news_bot import main as main_module
from ai_news_bot.config import load_config
from ai_news_bot.models import NewsItem
from ai_news_bot.storage import NewsStore


REPORT = """# Archived weekly report
## 📦 GitHub Trending
1. [owner/first](https://github.com/owner/first) — First project.
2. [owner/second](https://github.com/owner/second) — Second project.
"""
SUCCESS = {"ok": True, "result": {"message_id": 42}}

# Separate CLI processes share only the temporary SQLite file, never live services.
RECOVERY_PROCESS = """
import contextlib, io, json, sys
from unittest.mock import Mock, patch
from ai_news_bot import main
config, report, responses = sys.argv[1:]
responses = iter(json.loads(responses))
calls = []
def post(url, **kwargs):
    calls.append(kwargs['json']['text'])
    response = next(responses)
    if response == 'network-error':
        raise RuntimeError('connection failed: ' + url)
    return Mock(status_code=200, json=lambda: response)
out, err = io.StringIO(), io.StringIO()
with contextlib.ExitStack() as stack:
    for name in ('build_report', 'collect_items', 'summarize_with_llm', 'upload_report_files',
                 'publish_report_to_blog', 'send_remote_push', 'send_pushplus', 'mark_items_seen'):
        stack.enter_context(patch.object(main, name, side_effect=AssertionError(name + ' called')))
    client = stack.enter_context(patch('httpx.Client'))
    client.return_value.__enter__.return_value.post.side_effect = post
    sys.argv = ['news', '--config', config, '--sources', 'missing-sources.json', '--retry-telegram', report]
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = main.main()
print(json.dumps({'result': json.loads(out.getvalue()), 'errors': err.getvalue(), 'calls': calls}))
raise SystemExit(status)
"""


class TelegramRecoveryTests(unittest.TestCase):
    def config(self, root, **extra):
        path = root / "config.json"
        data = {
            "database_path": str(root / "news.sqlite3"),
            "telegram": {"enabled": True, "chat_id": "@original-channel", "bot_token_env": "TEST_TG_TOKEN"},
        }
        data.update(extra)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def retry_process(self, config, report, responses):
        run = subprocess.run(
            [sys.executable, "-c", RECOVERY_PROCESS, str(config), str(report), json.dumps(responses)],
            capture_output=True, text=True, timeout=10,
            env={"PATH": os.environ.get("PATH", ""), "TEST_TG_TOKEN": "synthetic-secret-token"},
        )
        self.assertFalse(run.stderr, run.stderr)
        self.assertNotIn("synthetic-secret-token", run.stdout)
        self.assertNotIn("/bot", run.stdout)
        return run.returncode, json.loads(run.stdout)

    def test_partial_delivery_recovers_only_remaining_entry_across_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.config(root)
            report = root / "2026-W40.md"
            report.write_text(REPORT, encoding="utf-8")
            receipt = root / "grok-published-2026-W40.json"
            receipt.write_text('{"published":true}', encoding="utf-8")
            with NewsStore(str(root / "news.sqlite3")) as store:
                store.mark_telegram_github_sent([("https://github.com/owner/first", "first")], "@other-channel")

            status, output = self.retry_process(config, report, [SUCCESS, "network-error"])
            self.assertEqual(status, 2)
            self.assertEqual(output["result"]["telegram"], {"ok": False, "sent": 1, "failed": 1, "skipped": 0})
            with NewsStore(str(root / "news.sqlite3")) as store:
                self.assertEqual(store.filter_unsent_telegram_github(
                    ["https://github.com/owner/first", "https://github.com/owner/second"], "@original-channel",
                ), ["https://github.com/owner/second"])

            status, output = self.retry_process(config, report, [SUCCESS])
            self.assertEqual(status, 0)
            self.assertEqual(len(output["calls"]), 1)
            self.assertIn("owner/second", output["calls"][0])
            self.assertEqual(output["result"]["telegram"], {"ok": True, "sent": 1, "failed": 0, "skipped": 1})
            status, output = self.retry_process(config, report, [])
            self.assertEqual(status, 0)
            self.assertEqual(output["calls"], [])
            self.assertEqual(output["result"]["telegram"]["skipped"], 2)
            self.assertEqual(report.read_text(encoding="utf-8"), REPORT)
            self.assertEqual(receipt.read_text(encoding="utf-8"), '{"published":true}')

    def test_normal_publish_records_failure_without_regenerating_published_week(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "TEST_TG_TOKEN": "synthetic-secret-token", "TEST_PUSH_KEY": "synthetic-push-key",
        }):
            root = Path(directory)
            config = self.config(root, llm={"provider": "grok-build"},
                                 scripting_push={"enabled": True, "api_key_env": "TEST_PUSH_KEY"},
                                 report={"output_dir": str(root / "reports")})
            argv = ["news", "--config", str(config), "--send", "--no-r2"]
            with patch("sys.argv", argv), patch.object(main_module, "build_report", return_value=(REPORT, [
                NewsItem(title="first", url="https://github.com/owner/first", source="GitHub"),
            ])), patch.object(main_module, "send_remote_push", return_value={"ok": True}), patch("httpx.Client") as client, \
                    patch("sys.stdout", new_callable=io.StringIO) as out, patch("sys.stderr", new_callable=io.StringIO):
                client.return_value.__enter__.return_value.post.side_effect = RuntimeError("synthetic-secret-token")
                self.assertEqual(main_module.main(), 2)
                result = json.loads(out.getvalue())
                self.assertEqual(result["telegram"], {"ok": False, "sent": 0, "failed": 2, "skipped": 0})
            receipts = list(root.glob("grok-published-*.json"))
            self.assertEqual(len(receipts), 1)
            self.assertEqual(json.loads(receipts[0].read_text())["telegram"], result["telegram"])
            with patch("sys.argv", argv), patch.object(main_module, "build_report") as build, patch("sys.stdout", io.StringIO()):
                self.assertEqual(main_module.main(), 0)
                build.assert_not_called()

    def test_receipt_commit_failure_stops_before_next_message(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"TEST_TG_TOKEN": "synthetic-token"}):
            config = load_config(self.config(Path(directory)), require_llm=False)
            with patch("httpx.Client") as client, \
                    patch.object(NewsStore, "mark_telegram_github_sent", side_effect=sqlite3.OperationalError("disk full")), \
                    patch("sys.stderr", io.StringIO()):
                post = client.return_value.__enter__.return_value.post
                post.return_value.json.return_value = SUCCESS
                result = main_module.send_report_telegram(REPORT, config)
                self.assertFalse(result.ok)
                self.assertEqual(result.sent, 0)
                self.assertEqual(result.failed, 2)
                self.assertEqual(post.call_count, 1)

    def test_missing_report_and_disabled_telegram_fail_without_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.config(root)
            report = root / "missing.md"
            with patch("sys.argv", ["news", "--config", str(config), "--retry-telegram", str(report)]), \
                    patch.object(main_module, "build_report") as build, patch("sys.stdout", io.StringIO()):
                self.assertEqual(main_module.main(), 2)
                build.assert_not_called()
            report.write_text(REPORT)
            config = self.config(root, telegram={"enabled": False})
            with patch("sys.argv", ["news", "--config", str(config), "--retry-telegram", str(report)]), \
                    patch.object(main_module, "send_telegram_messages") as send, patch("sys.stdout", io.StringIO()):
                self.assertEqual(main_module.main(), 2)
                send.assert_not_called()
