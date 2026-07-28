import unittest

from ai_news_bot.models import NewsItem
from ai_news_bot.report_postprocess import (
    is_fluff_description,
    sanitize_github_sections,
    strip_trailing_source_for_github,
)


class ReportPostprocessTests(unittest.TestCase):
    def test_strip_trailing_source_for_github(self):
        text = "记忆 OS，省 token。（来源：[GitHub 兴趣推荐](https://github.com/a/b)）"
        self.assertEqual(
            strip_trailing_source_for_github(text),
            "记忆 OS，省 token。",
        )

    def test_is_fluff_description(self):
        self.assertTrue(is_fluff_description("具体功能待探索，值得持续关注"))
        self.assertFalse(is_fluff_description("Rust 单二进制 Telegram 审批网关"))

    def test_sanitize_github_sections_fixes_source_tail_and_fluff(self):
        report = "\n".join(
            [
                "# 📡 Furina · 每日科技/AI日报",
                "2026年7月28日",
                "",
                "## 📦 GitHub Trending",
                "1. [a/b](https://github.com/a/b) 具体功能待探索",
                "2. not-a-github-line",
                "",
                "## ⭐ 你可能感兴趣",
                "1. [c/d](https://github.com/c/d) 好工具。（来源：[GitHub 兴趣推荐](https://github.com/c/d)）",
            ]
        )
        selected = [
            NewsItem(
                title="a/b",
                url="https://github.com/a/b",
                source="GitHub Trending",
                category="GitHub Trending",
                summary="分布式数据库，线性扩展",
            ),
            NewsItem(
                title="c/d",
                url="https://github.com/c/d",
                source="GitHub 兴趣推荐",
                category="你可能感兴趣",
                summary="MCP 记忆服务器",
            ),
        ]
        fixed = sanitize_github_sections(report, selected)
        self.assertIn("1. [a/b](https://github.com/a/b) 分布式数据库，线性扩展", fixed)
        self.assertIn("[c/d](https://github.com/c/d)", fixed)
        self.assertTrue("MCP 记忆服务器" in fixed or "好工具" in fixed)
        self.assertNotIn("来源：", fixed)
        self.assertNotIn("具体功能待探索", fixed)
        self.assertNotIn("not-a-github-line", fixed)


if __name__ == "__main__":
    unittest.main()
