from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from astrbot import logger
from astrbot.api.all import Star, Context, register, AstrMessageEvent, MessageChain
from astrbot.api.event import filter
from astrbot.core.star.star_tools import StarTools

from .ai_news_bot.fetch_rss import fetch_rss_feed
from .ai_news_bot.fetch_hn import fetch_hacker_news
from .ai_news_bot.fetch_github import fetch_github_trending
from .ai_news_bot.dedupe import dedupe_items
from .ai_news_bot.rank import rank_items
from .ai_news_bot.render import render_fallback_report
from .ai_news_bot.storage import NewsStore
from .ai_news_bot.models import NewsItem


SYSTEM_PROMPT = """你是严谨的中文科技日报编辑。
请根据用户提供的候选新闻生成中文日报，英文标题和摘要必须翻译或改写为中文。
硬性规则：
1. 只使用候选新闻中的事实，不得编造公司名、数字、日期、融资金额或发布内容。
2. 单来源重大新闻必须标注"未交叉验证"。
3. 日报头部使用 "# 📡 Furina · 每日科技/AI日报"（Markdown 一级标题）。
4. 输出固定三节，节标题分别是：## 🔥 科技热点 / ## 🤖 AI动态 / ## 📦 GitHub Trending。
5. 【数量要求】科技热点 6~8 条，AI动态 6~8 条，GitHub Trending 恰好 5 条。
6. 【序号要求】每节内部必须用 1. 2. 3. 阿拉伯数字编号，从 1 开始，禁止用项目符号（-）或字母。
7. 【格式要求】每条正文写 1~2 句说明"发生了什么"和"为什么值得看"，控制在 80~150 个中文字符。
8. 【来源标注】科技热点和 AI动态 每条末尾加括号注明来源媒体，格式：（来源：媒体名）。不要输出完整 URL。
9. 【GitHub 链接】候选新闻中每条 GitHub Trending 条目已提供"仓库链接（必须原样保留）"字段，输出时必须将该 Markdown 链接原样放在正文之前，禁止修改或省略链接。
10. 重要词语或关键数字可用 **加粗**。
"""


def _format_items(items: list[NewsItem]) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        if item.category == "GitHub Trending":
            # 预格式化 markdown 链接，LLM 直接复制，无需自行生成
            link = f"[{item.title}]({item.url})"
            lines.append(
                "\n".join(
                    [
                        f"{index}. 分类：GitHub Trending",
                        f"   仓库链接（必须原样保留）：{link}",
                        f"   摘要：{item.summary or '无'}",
                    ]
                )
            )
        else:
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

输出骨架（严格按此格式，不要增删节标题）：
# 📡 Furina · 每日科技/AI日报
{date_label}

---

## 🔥 科技热点

1. 正文内容。（来源：媒体名）
2. 正文内容。（来源：媒体名）
（共 6~8 条）

## 🤖 AI动态

1. 正文内容。（来源：媒体名）
2. 正文内容。（来源：媒体名）
（共 6~8 条）

## 📦 GitHub Trending

1. [用户名/仓库名](https://github.com/用户名/仓库名) 正文一两句描述。
2. [用户名/仓库名](https://github.com/用户名/仓库名) 正文一两句描述。
（恰好 5 条，每条都要有 GitHub 链接）
"""


def _is_item_line(line: str) -> bool:
    if not line.strip():
        return False
    if line.startswith('#'):
        return False
    if re.match(r'^[-─=*]{3,}$', line.strip()):
        return False
    if line[0] in (' ', '\t'):
        return False
    if line.strip().startswith('（'):
        return False
    if re.match(r'^\d{4}年', line):
        return False
    return True


def _strip_item_prefix(line: str) -> str:
    m = re.match(r'^\d+\.\s+(.*)', line, re.DOTALL)
    if m:
        return m.group(1)
    m = re.match(r'^[-•]\s+(.*)', line, re.DOTALL)
    if m:
        return m.group(1)
    return line


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
        self._plugin_dir = Path(__file__).parent
        self._data_dir: Path | None = None
        self._cron_job_name = "astrbot_plugin_ai_news_bot_daily"
        self._cron_job_id: str | None = None

    async def initialize(self):
        self._data_dir = StarTools.get_data_dir("astrbot_plugin_ai_news_bot")
        self._data_dir.mkdir(parents=True, exist_ok=True)

        schedule_time = str(self._conf("schedule_time", "") or "").strip()
        if not schedule_time:
            return
        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            return
        try:
            job = await cron_manager.add_basic_job(
                name=self._cron_job_name,
                cron_expression=self._schedule_to_cron(schedule_time),
                handler=self._daily_push,
                description="AI科技日报每日定时推送",
                timezone="Asia/Shanghai",
                persistent=False,
            )
            self._cron_job_id = job.job_id
        except Exception as e:
            logger.error(f"[AI News Bot] 注册定时任务失败：{e}")

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

    def _fix_numbering(self, report: str) -> str:
        """强制为 LLM 每节条目编号（适配无标记、- 符号、已有序号三种格式）。"""
        chunks = re.split(r'(\n##\s[^\n]+)', report)
        result = []
        in_section = False
        for chunk in chunks:
            if chunk.startswith('\n##'):
                in_section = True
                result.append(chunk)
                continue
            if not in_section:
                result.append(chunk)
                continue
            lines = chunk.split('\n')
            counter = 0
            new_lines = []
            for line in lines:
                if _is_item_line(line):
                    counter += 1
                    content = _strip_item_prefix(line)
                    new_lines.append(f"{counter}. {content}")
                else:
                    new_lines.append(line)
            result.append('\n'.join(new_lines))
        return ''.join(result)

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
        if not provider_id:
            logger.warning("[AI News Bot] provider_id 未配置，使用回退模式（无 LLM）")
        else:
            try:
                content = await self._llm_summarize(provider_id, items, date_label)
            except Exception as e:
                logger.error(f"[AI News Bot] LLM 调用失败，回退为原文模式：{e}")

        if not content:
            # 回退模式：限制每节条目数，避免 GitHub Trending 大量溢出
            from collections import defaultdict
            grouped: dict[str, list[NewsItem]] = defaultdict(list)
            for item in items:
                grouped[item.category or "科技热点"].append(item)
            fallback_items: list[NewsItem] = []
            for cat, cat_items in grouped.items():
                cap = 5 if cat == "GitHub Trending" else 8
                fallback_items.extend(cat_items[:cap])
            content = render_fallback_report(fallback_items, date_label)

        content = self._fix_numbering(content)

        if mark_seen and items:
            await asyncio.to_thread(self._mark_seen_sync, data_dir, items)
        return content

    async def _daily_push(self):
        try:
            content = await self._run_report(mark_seen=True)
        except Exception as e:
            logger.error(f"[AI News Bot] 定时生成日报失败：{e}")
            return
        raw = str(self._conf("schedule_targets", "") or "")
        targets = [t.strip() for t in re.split(r"[\n,]+", raw) if t.strip()]
        if not targets:
            logger.warning("[AI News Bot] 未配置 schedule_targets，跳过定时推送")
            return
        for session_id in targets:
            for section in self._split_sections(content):
                try:
                    await self.context.send_message(session_id, MessageChain().message(section))
                except Exception as e:
                    logger.error(f"[AI News Bot] 推送到 {session_id} 失败：{e}")

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
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            raise ValueError("schedule_time 时间无效")
        return f"{minute} {hour} * * *"

    def _date_label(self) -> str:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        return f"{now.year}年{now.month}月{now.day}日"
