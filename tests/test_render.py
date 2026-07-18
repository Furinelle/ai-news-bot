import unittest

from ai_news_bot.models import NewsItem
from ai_news_bot.render import fix_numbering, render_fallback_report, render_html_report, strip_markdown_emphasis


class RenderTests(unittest.TestCase):
    def test_render_fallback_report_links_sources_but_not_plain_news_titles(self):
        report = render_fallback_report(
            [
                NewsItem(
                    title="OpenAI releases a realtime model",
                    url="https://example.com/openai",
                    source="Example",
                    category="AI动态",
                ),
                NewsItem(
                    title="A repository is trending",
                    url="https://github.com/example/repo",
                    source="GitHub Trending",
                    category="GitHub Trending",
                ),
            ],
            date_label="2026年5月9日",
        )

        self.assertIn("# 📡 Furina · 每日科技/AI日报", report)
        self.assertIn("2026年5月9日", report)
        self.assertIn("## 🤖 AI动态", report)
        self.assertIn("## 📦 GitHub Trending", report)
        self.assertIn("1. OpenAI releases a realtime model", report)
        self.assertIn("（来源：[Example](https://example.com/openai)）", report)
        self.assertNotIn("[OpenAI releases a realtime model](https://example.com/openai)", report)
        self.assertIn("[A repository is trending](https://github.com/example/repo)", report)
        self.assertIn("---\n由 AI News Bot 自动生成", report)
        self.assertNotIn("2. 由 AI News Bot 自动生成", report)

        html = render_html_report(report)
        self.assertIn('<a href="https://example.com/openai" rel="noopener noreferrer">Example</a>', html)
        self.assertIn('role="tablist"', html)
        self.assertIn('role="tab"', html)
        self.assertIn('role="tabpanel"', html)
        self.assertIn('id="section-0"', html)
        self.assertIn('id="section-1"', html)
        self.assertIn('class="tab-button is-active"', html)
        self.assertIn('hidden><h2>📦 GitHub Trending</h2>', html)

    def test_strip_markdown_emphasis_removes_bold_markers(self):
        text = strip_markdown_emphasis("**重点** 和 __项目__")

        self.assertEqual(text, "重点 和 项目")

    def test_fix_numbering_normalizes_unnumbered_and_bulleted_section_items(self):
        report = "\n".join(
            [
                "# 📡 Furina · 每日科技/AI日报",
                "2026年5月9日",
                "",
                "## 🔥 科技热点",
                "The first item",
                "- The second item",
                "3、The third item",
                "",
                "## 📦 GitHub Trending",
                "[example/repo](https://github.com/example/repo) Repository summary",
            ]
        )

        fixed = fix_numbering(report)

        self.assertIn("1. The first item", fixed)
        self.assertIn("2. The second item", fixed)
        self.assertIn("3. The third item", fixed)
        self.assertIn("1. [example/repo](https://github.com/example/repo) Repository summary", fixed)

    def test_fix_numbering_restarts_numbering_for_each_section(self):
        report = "\n".join(
            [
                "# 📡 Furina · 每日科技/AI日报",
                "",
                "## 🔥 科技热点",
                "Tech one",
                "Tech two",
                "",
                "## 🤖 AI动态",
                "AI one",
                "AI two",
                "",
                "## 📦 GitHub Trending",
                "Repo one",
                "Repo two",
            ]
        )

        fixed = fix_numbering(report)

        self.assertIn("## 🔥 科技热点\n1. Tech one\n2. Tech two", fixed)
        self.assertIn("## 🤖 AI动态\n1. AI one\n2. AI two", fixed)
        self.assertIn("## 📦 GitHub Trending\n1. Repo one\n2. Repo two", fixed)

    def test_fix_numbering_normalizes_plain_section_headings(self):
        report = "\n".join(
            [
                "# 📡 Furina · 每日科技/AI日报",
                "",
                "科技热点",
                "Tech one",
                "Tech two",
                "",
                "AI动态",
                "- AI one",
                "- AI two",
                "",
                "GitHub Trending",
                "Repo one",
                "Repo two",
            ]
        )

        fixed = fix_numbering(report)

        self.assertIn("## 🔥 科技热点\n1. Tech one\n2. Tech two", fixed)
        self.assertIn("## 🤖 AI动态\n1. AI one\n2. AI two", fixed)
        self.assertIn("## 📦 GitHub Trending\n1. Repo one\n2. Repo two", fixed)

    def test_render_fallback_report_keeps_ten_github_trending_items(self):
        report = render_fallback_report(
            [
                NewsItem(
                    title=f"Repo {index}",
                    url=f"https://github.com/example/repo-{index}",
                    source="GitHub Trending",
                    category="GitHub Trending",
                )
                for index in range(1, 11)
            ],
            date_label="2026年5月14日",
        )

        self.assertIn("10. [Repo 10](https://github.com/example/repo-10)", report)


if __name__ == "__main__":
    unittest.main()
