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
from .ai_news_bot.help import build_news_help
from .ai_news_bot.rank import select_report_items
from .ai_news_bot.render import fix_numbering, render_fallback_report
from .ai_news_bot.schedule import (
    add_subscription,
    normalize_schedule_time,
    remove_subscription,
    resolve_schedule_settings,
)
from .ai_news_bot.storage import NewsStore
from .ai_news_bot.models import NewsItem


SCHEDULE_KV_KEY = "schedule_settings"


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
        await self._register_daily_job()

    async def _get_saved_schedule_state(self) -> dict[str, Any] | None:
        state = await self.get_kv_data(SCHEDULE_KV_KEY, None)
        return state if isinstance(state, dict) else None

    async def _save_schedule_state(self, state: dict[str, Any]) -> None:
        await self.put_kv_data(SCHEDULE_KV_KEY, state)

    async def _resolve_schedule_settings(self):
        return resolve_schedule_settings(
            config_time=str(self._conf("schedule_time", "") or ""),
            config_targets=str(self._conf("schedule_targets", "") or ""),
            saved_state=await self._get_saved_schedule_state(),
        )

    async def _register_daily_job(self):
        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            logger.error("[AI News Bot] AstrBot context 中没有 cron_manager，无法注册定时任务")
            return
        try:
            await self._delete_existing_daily_jobs(cron_manager)
            settings = await self._resolve_schedule_settings()
            if not settings.schedule_time:
                logger.info("[AI News Bot] 未配置 schedule_time，定时推送未启用")
                return
            if not settings.targets:
                logger.warning("[AI News Bot] 未配置定时推送目标，定时推送未启用")
                return
            job = await cron_manager.add_basic_job(
                name=self._cron_job_name,
                cron_expression=self._schedule_to_cron(settings.schedule_time),
                handler=self._daily_push,
                description="AI科技日报每日定时推送",
                timezone="Asia/Shanghai",
                persistent=False,
            )
            self._cron_job_id = job.job_id
            logger.info(
                f"[AI News Bot] 已注册每日定时推送：{settings.schedule_time} Asia/Shanghai，"
                f"目标 {len(settings.targets)} 个（来源：{settings.source}）"
            )
        except Exception as e:
            logger.error(f"[AI News Bot] 注册定时任务失败：{e}")

    async def terminate(self):
        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            return
        await self._delete_existing_daily_jobs(cron_manager)

    async def _delete_existing_daily_jobs(self, cron_manager: Any):
        if self._cron_job_id:
            await cron_manager.delete_job(self._cron_job_id)
            self._cron_job_id = None
        for job in await cron_manager.list_jobs("basic"):
            if getattr(job, "name", None) == self._cron_job_name:
                await cron_manager.delete_job(job.job_id)

    def _fix_numbering(self, report: str) -> str:
        return fix_numbering(report)

    def _split_sections(self, report: str) -> list[str]:
        import re
        parts = re.split(r'\n(?=##\s)', report)
        parts = [p.strip() for p in parts if p.strip()]
        return parts if len(parts) > 1 else [report]

    @filter.command("news")
    async def handle_news_cmd(self, event: AstrMessageEvent):
        logger.info(f"[AI News Bot] 当前会话 unified_msg_origin：{event.unified_msg_origin}")
        yield event.plain_result("正在生成今日科技/AI日报，请稍等。")
        try:
            result = await self._run_report(mark_seen=True)
        except Exception as exc:
            result = f"日报生成失败：{exc}"
        for section in self._split_sections(result):
            yield event.plain_result(section)

    @filter.command("news_help")
    async def handle_news_help_cmd(self, event: AstrMessageEvent):
        yield event.plain_result(build_news_help())

    @filter.command("newsid")
    async def handle_newsid_cmd(self, event: AstrMessageEvent):
        yield event.plain_result(
            f"当前会话 ID：{event.unified_msg_origin}\n"
            "把它填入插件配置 schedule_targets，可用于每日定时推送。"
        )

    @filter.command("news_subscribe")
    async def handle_news_subscribe_cmd(self, event: AstrMessageEvent, schedule_time: str = ""):
        try:
            if schedule_time:
                target_time = normalize_schedule_time(schedule_time)
            else:
                settings = await self._resolve_schedule_settings()
                target_time = settings.schedule_time
            if not target_time:
                yield event.plain_result("请指定推送时间，例如：/news_subscribe 08:30")
                return
            state = add_subscription(
                saved_state=await self._get_saved_schedule_state(),
                config_targets=str(self._conf("schedule_targets", "") or ""),
                target=event.unified_msg_origin,
                schedule_time=target_time,
            )
            await self._save_schedule_state(state)
            await self._register_daily_job()
            yield event.plain_result(f"已订阅当前会话，每天 {state['schedule_time']} 推送科技/AI日报。")
        except ValueError as exc:
            yield event.plain_result(f"订阅失败：{exc}")

    @filter.command("news_unsubscribe")
    async def handle_news_unsubscribe_cmd(self, event: AstrMessageEvent):
        state = remove_subscription(
            saved_state=await self._get_saved_schedule_state(),
            config_targets=str(self._conf("schedule_targets", "") or ""),
            target=event.unified_msg_origin,
        )
        await self._save_schedule_state(state)
        await self._register_daily_job()
        yield event.plain_result("已取消当前会话的每日推送。")

    @filter.command("news_schedule")
    async def handle_news_schedule_cmd(self, event: AstrMessageEvent):
        settings = await self._resolve_schedule_settings()
        current_enabled = event.unified_msg_origin in settings.targets
        if not settings.schedule_time:
            yield event.plain_result("每日推送未启用。使用 /news_subscribe 08:30 可订阅当前会话。")
            return
        yield event.plain_result(
            f"每日推送时间：{settings.schedule_time}\n"
            f"订阅会话数：{len(settings.targets)}\n"
            f"当前会话：{'已订阅' if current_enabled else '未订阅'}"
        )

    async def _run_report(self, mark_seen: bool = True) -> str:
        data_dir = self._ensure_data_dir()
        sources = await asyncio.to_thread(self._load_sources_sync)
        max_items = int(self._conf("max_report_items", 30) or 30)

        candidates = await asyncio.to_thread(self._collect_items_sync, sources, max_items)
        new_items = await asyncio.to_thread(self._filter_seen_sync, data_dir, candidates)
        items = select_report_items(new_items, max_items)
        minimum_report_items = min(max_items, 17)
        if len(items) < minimum_report_items:
            selected_urls = {item.url for item in items}
            top_up_items = [item for item in candidates if item.url not in selected_urls]
            items = select_report_items(items + top_up_items, max_items)
            logger.info(
                f"[AI News Bot] 新内容不足 {minimum_report_items} 条，已使用候选池补齐至 {len(items)} 条"
            )

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
        settings = await self._resolve_schedule_settings()
        targets = settings.targets
        if not targets:
            logger.warning("[AI News Bot] 未配置定时推送目标，跳过定时推送")
            return
        for session_id in targets:
            for section in self._split_sections(content):
                try:
                    sent = await self.context.send_message(session_id, MessageChain().message(section))
                    if not sent:
                        logger.error(f"[AI News Bot] 未找到定时推送目标会话：{session_id}")
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

        return dedupe_items(items)

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
