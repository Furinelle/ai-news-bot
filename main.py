from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from astrbot.api.all import Star, Context, register, AstrMessageEvent
from astrbot.api.event import filter
from astrbot.core.star.star_tools import StarTools

from ai_news_bot.fetch_rss import fetch_rss_feed
from ai_news_bot.fetch_hn import fetch_hacker_news
from ai_news_bot.fetch_github import fetch_github_trending
from ai_news_bot.dedupe import dedupe_items
from ai_news_bot.rank import rank_items
from ai_news_bot.render import render_fallback_report
from ai_news_bot.storage import NewsStore
from ai_news_bot.models import NewsItem

try:
    from ai_news_bot.pushplus import send_pushplus
except ImportError:
    send_pushplus = None


SYSTEM_PROMPT = """你是严谨的中文科技日报编辑。
请根据用户提供的候选新闻生成中文日报，英文标题和摘要必须翻译或改写为中文。
硬性规则：
1. 只使用候选新闻中的事实，不得编造公司名、数字、日期、融资金额或发布内容。
2. 普通新闻不要输出链接，只保留来源名；只有 GitHub Trending 条目可以输出 GitHub 仓库链接（用 Markdown 格式 [repo](url)）。
3. 单来源重大新闻必须标注未交叉验证。
4. 输出分为固定三节，各节标题必须分别是：## 🔥 科技热点 / ## 🤖 AI动态 / ## 📦 GitHub Trending。
5. 每条写成1到2句，说明发生了什么和为什么值得看，控制在120到180个中文字符。
6. 日报头部使用 "# 📡 Furina · 每日科技/AI日报"（一级标题）。
7. 使用 Markdown 格式：用 ## 作为节标题，列表用 1. 2. 3. 编号，重要词语可用 **加粗**。
8. 每个分区内编号从1重新开始。
"""


def _format_items(items: list[NewsItem]) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(
            "\n".join(
                [
                    f"{index}. 标题：{item.title}",
                    f"   分类：{item.category}",
                    f"   来源：{item.source}",
                    f"   链接：{item.url}",
                    f"   摘要：{item.summary or '无'}",
                ]
            )
        )
    return "\n".join(lines)


def _build_user_prompt(items: list[NewsItem], date_label: str) -> str:
    return f"""请把以下候选新闻整理成日报。
日报日期：{date_label}
必须原样使用这个日期，不要自行推断、改写或替换日期。

候选新闻：
{_format_items(items)}

请直接输出日报正文，不要解释生成过程。内容要比快讯更耐读，但仍然适合微信消息阅读。

输出骨架：
# 📡 Furina · 每日科技/AI日报
{date_label}

---

## 🔥 科技热点

1. ...
2. ...

## 🤖 AI动态

1. ...
2. ...

## 📦 GitHub Trending

1. ...
2. ...
"""


@register(
    "astrbot_plugin_ai_news_bot",
    "Furinelle",
    "每日科技/AI日报",
    "1.0.0",
    "https://github.com/Furinelle/ai-news-bot",
)
class AiNewsBotPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context)
        self.config = config or {}
        self._cron_job_name = "astrbot_plugin_ai_news_bot_daily_push"
        self._cron_job_id: str | None = None
        self._plugin_dir = Path(__file__).parent
        self._data_dir: Path | None = None

    async def initialize(self):
        self._data_dir = StarTools.get_data_dir("astrbot_plugin_ai_news_bot")
        self._data_dir.mkdir(parents=True, exist_ok=True)

        schedule_time = str(self._conf("schedule_time", "") or "").strip()
        if not schedule_time:
            return

        cron_expression = self._schedule_to_cron(schedule_time)
        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            return

        job = await cron_manager.add_basic_job(
            name=self._cron_job_name,
            cron_expression=cron_expression,
            handler=self._daily_push,
            description="AI科技日报每日定时推送",
            timezone="Asia/Shanghai",
            persistent=False,
        )
        self._cron_job_id = getattr(job, "job_id", None)

    async def terminate(self):
        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            return

        if self._cron_job_id:
            await cron_manager.delete_job(self._cron_job_id)
            self._cron_job_id = None
            return

        for job in await cron_manager.list_jobs("basic"):
            if getattr(job, "name", None) == self._cron_job_name:
                await cron_manager.delete_job(job.job_id)

    def _split_sections(self, report: str) -> list[str]:
        import re
        parts = re.split(r'\n(?=##\s)', report)
        parts = [p.strip() for p in parts if p.strip()]
        return parts if len(parts) > 1 else [report]

    @filter.command("news")
    async def handle_news_cmd(self, event: AstrMessageEvent):
        yield event.plain_result("正在生成今日科技/AI日报，请稍等。")
        try:
            result = await self._run_report(mark_seen=True)
        except Exception as exc:
            result = f"日报生成失败：{exc}"
        for section in self._split_sections(result):
            yield event.plain_result(section)

    async def _run_report(self, mark_seen: bool = True) -> str:
        data_dir = self._ensure_data_dir()
        sources = await asyncio.to_thread(self._load_sources_sync)
        max_items = int(self._conf("max_report_items", 18) or 18)

        items = await asyncio.to_thread(self._collect_items_sync, sources, max_items)
        items = await asyncio.to_thread(self._filter_seen_sync, data_dir, items)

        date_label = self._date_label()
        provider_id = str(self._conf("provider_id", "") or "").strip()
        content = ""
        if provider_id:
            try:
                content = await self._llm_summarize(provider_id, items, date_label)
            except Exception:
                content = ""

        if not content:
            content = render_fallback_report(items, date_label)

        if mark_seen and items:
            await asyncio.to_thread(self._mark_seen_sync, data_dir, items)
        return content

    async def _llm_summarize(
        self,
        provider_id: str,
        items: list[NewsItem],
        date_label: str,
    ) -> str:
        system_prompt = SYSTEM_PROMPT
        user_prompt = _build_user_prompt(items, date_label)
        response = await self.context.llm_generate(
            chat_provider_id=provider_id,
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        return str(response.completion_text).strip()

    async def _daily_push(self):
        content = await self._run_report(mark_seen=True)
        if not self._conf("enable_pushplus", False):
            return
        if send_pushplus is None:
            return

        token = str(self._conf("pushplus_token", "") or "").strip()
        if not token:
            return

        channel = str(self._conf("pushplus_channel", "clawbot") or "clawbot").strip()
        title = "📡 Furina · 每日科技/AI日报"
        await asyncio.to_thread(
            send_pushplus,
            token,
            title,
            content,
            channel,
            "markdown",
        )

    def _conf(self, key: str, default: Any = None) -> Any:
        if isinstance(self.config, dict):
            return self.config.get(key, default)
        getter = getattr(self.config, "get", None)
        if callable(getter):
            return getter(key, default)
        return getattr(self.config, key, default)

    def _ensure_data_dir(self) -> Path:
        if self._data_dir is None:
            self._data_dir = StarTools.get_data_dir("astrbot_plugin_ai_news_bot")
            self._data_dir.mkdir(parents=True, exist_ok=True)
        return self._data_dir

    def _load_sources_sync(self) -> dict[str, Any]:
        data_dir = self._ensure_data_dir()
        target = data_dir / "sources.json"
        if not target.exists():
            shutil.copy2(self._plugin_dir / "sources.json", target)
        return json.loads(target.read_text(encoding="utf-8"))

    def _collect_items_sync(
        self,
        sources: dict[str, Any],
        max_items: int,
    ) -> list[NewsItem]:
        items: list[NewsItem] = []

        for rss in sources.get("rss", []):
            rss_items = fetch_rss_feed(
                url=rss["url"],
                source=rss["name"],
                category=rss.get("category", "科技热点"),
            )
            items.extend(rss_items[: int(rss.get("limit", 20))])

        hn = sources.get("hacker_news", {})
        if hn.get("enabled", True):
            items.extend(fetch_hacker_news(limit=int(hn.get("limit", 20))))

        github = sources.get("github_trending", {})
        if github.get("enabled", True):
            since = str(github.get("since", "daily") or "daily")
            limit = int(github.get("limit", 10))
            for language in github.get("languages", [""]):
                items.extend(
                    fetch_github_trending(
                        language=str(language or ""),
                        since=since,
                        limit=limit,
                    )
                )

        return rank_items(dedupe_items(items), max_items)

    def _filter_seen_sync(
        self,
        data_dir: Path,
        items: list[NewsItem],
    ) -> list[NewsItem]:
        with NewsStore(str(data_dir / "news_seen.sqlite3")) as store:
            is_seen = getattr(store, "is_seen", None)
            if callable(is_seen):
                new_items: list[NewsItem] = []
                for item in items:
                    try:
                        seen = is_seen(item)
                    except TypeError:
                        seen = is_seen(item.url)
                    if not seen:
                        new_items.append(item)
                return new_items

            filter_new = getattr(store, "filter_new", None)
            if callable(filter_new):
                return filter_new(items)

            return items

    def _mark_seen_sync(self, data_dir: Path, items: list[NewsItem]) -> None:
        with NewsStore(str(data_dir / "news_seen.sqlite3")) as store:
            store.mark_seen(items)

    def _schedule_to_cron(self, schedule_time: str) -> str:
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", schedule_time)
        if not match:
            raise ValueError("schedule_time 必须是 HH:MM 格式")
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour > 23 or minute > 59:
            raise ValueError("schedule_time 必须是有效的 HH:MM 时间")
        return f"{minute} {hour} * * *"

    def _date_label(self) -> str:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        return f"{now.year}年{now.month}月{now.day}日"
