from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    timeout_seconds: float = 180.0
    thinking_enabled: bool = False
    reasoning_effort: str = "high"


@dataclass(frozen=True)
class PushplusConfig:
    token: str = ""
    channel: str = "clawbot"
    template: str = "markdown"


@dataclass(frozen=True)
class ScriptingPushConfig:
    enabled: bool = False
    api_key: str = ""
    endpoint: str = "https://push.scripting.fun/push"
    title: str = "Furina · 每日科技/AI日报"


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    endpoint_base: str = "https://api.telegram.org"
    disable_web_page_preview: bool = False


@dataclass(frozen=True)
class BlogConfig:
    enabled: bool = False
    base_url: str = ""
    username: str = ""
    password: str = ""
    title_prefix: str = "每日科技 / AI 日报"
    tags: tuple[str, ...] = ("每日新闻", "AI", "科技")


@dataclass(frozen=True)
class R2Config:
    enabled: bool = False
    bucket: str = ""
    endpoint_url: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    key_prefix: str = "daily"
    public_base_url: str = ""
    presigned_url_expires_seconds: int = 604800
    content_type: str = "text/markdown; charset=utf-8"


@dataclass(frozen=True)
class LimitsConfig:
    max_items: int = 90
    max_report_items: int = 45


@dataclass(frozen=True)
class ReportConfig:
    output_dir: str = "reports"
    latest_name: str = "latest.md"


@dataclass(frozen=True)
class AppConfig:
    llm: LlmConfig
    pushplus: PushplusConfig
    scripting_push: ScriptingPushConfig
    telegram: TelegramConfig
    blog: BlogConfig
    r2: R2Config
    limits: LimitsConfig
    report: ReportConfig
    database_path: str = "data/news_history.sqlite3"


def _required_env(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {env_name}")
    return value


def _optional_env(env_name: str) -> str:
    if not env_name:
        return ""
    return os.environ.get(env_name, "").strip()


def _read_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config(path: str | Path) -> AppConfig:
    raw = _read_json(path)
    llm_raw = raw.get("llm", {})
    push_raw = raw.get("pushplus", {})
    scripting_push_raw = raw.get("scripting_push", {})
    telegram_raw = raw.get("telegram", {})
    blog_raw = raw.get("blog", {})
    r2_raw = raw.get("r2", {})
    limits_raw = raw.get("limits", {})
    report_raw = raw.get("report", {})

    llm = LlmConfig(
        base_url=str(llm_raw.get("base_url", "")).rstrip("/"),
        api_key=_required_env(str(llm_raw.get("api_key_env", "LLM_API_KEY"))),
        model=str(llm_raw.get("model", "")).strip(),
        temperature=float(llm_raw.get("temperature", 0.2)),
        timeout_seconds=float(llm_raw.get("timeout_seconds", 180)),
        thinking_enabled=bool(llm_raw.get("thinking_enabled", False)),
        reasoning_effort=str(llm_raw.get("reasoning_effort", "high")),
    )
    if not llm.base_url:
        raise ConfigError("llm.base_url is required")
    if not llm.model:
        raise ConfigError("llm.model is required")

    pushplus_token_env = str(push_raw.get("token_env", "PUSHPLUS_TOKEN"))
    pushplus = PushplusConfig(
        token=_optional_env(pushplus_token_env),
        channel=str(push_raw.get("channel", "clawbot")),
        template=str(push_raw.get("template", "markdown")),
    )

    scripting_push_enabled = bool(scripting_push_raw.get("enabled", False))
    scripting_push_api_key_env = str(scripting_push_raw.get("api_key_env", "SCRIPTING_PUSH_API_KEY"))
    scripting_push = ScriptingPushConfig(
        enabled=scripting_push_enabled,
        api_key=_optional_env(scripting_push_api_key_env),
        endpoint=str(scripting_push_raw.get("endpoint", "https://push.scripting.fun/push")),
        title=str(scripting_push_raw.get("title", "Furina · 每日科技/AI日报")),
    )

    telegram = TelegramConfig(
        enabled=bool(telegram_raw.get("enabled", False)),
        bot_token=_optional_env(str(telegram_raw.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))),
        chat_id=str(telegram_raw.get("chat_id", "")).strip(),
        endpoint_base=str(telegram_raw.get("endpoint_base", "https://api.telegram.org")).strip().rstrip("/"),
        disable_web_page_preview=bool(telegram_raw.get("disable_web_page_preview", False)),
    )

    blog = BlogConfig(
        enabled=bool(blog_raw.get("enabled", False)),
        base_url=str(blog_raw.get("base_url", "")).strip().rstrip("/"),
        username=_optional_env(str(blog_raw.get("username_env", "BLOG_ADMIN_USERNAME"))),
        password=_optional_env(str(blog_raw.get("password_env", "BLOG_ADMIN_PASSWORD"))),
        title_prefix=str(blog_raw.get("title_prefix", "每日科技 / AI 日报")).strip(),
        tags=tuple(str(tag).strip() for tag in blog_raw.get("tags", ["每日新闻", "AI", "科技"]) if str(tag).strip()),
    )

    r2_enabled = bool(r2_raw.get("enabled", False))
    account_id = _optional_env(str(r2_raw.get("account_id_env", "CLOUDFLARE_ACCOUNT_ID")))
    endpoint_url = str(r2_raw.get("endpoint_url", "")).strip()
    if not endpoint_url and account_id:
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
    r2 = R2Config(
        enabled=r2_enabled,
        bucket=str(r2_raw.get("bucket", "")).strip(),
        endpoint_url=endpoint_url,
        access_key_id=_optional_env(str(r2_raw.get("access_key_id_env", "R2_ACCESS_KEY_ID"))),
        secret_access_key=_optional_env(str(r2_raw.get("secret_access_key_env", "R2_SECRET_ACCESS_KEY"))),
        key_prefix=str(r2_raw.get("key_prefix", "daily")).strip().strip("/"),
        public_base_url=str(r2_raw.get("public_base_url", "")).strip().rstrip("/"),
        presigned_url_expires_seconds=int(r2_raw.get("presigned_url_expires_seconds", 604800)),
        content_type=str(r2_raw.get("content_type", "text/markdown; charset=utf-8")),
    )

    limits = LimitsConfig(
        max_items=int(limits_raw.get("max_items", 90)),
        max_report_items=int(limits_raw.get("max_report_items", 45)),
    )

    report = ReportConfig(
        output_dir=str(report_raw.get("output_dir", "reports")),
        latest_name=str(report_raw.get("latest_name", "latest.md")),
    )

    return AppConfig(
        llm=llm,
        pushplus=pushplus,
        scripting_push=scripting_push,
        telegram=telegram,
        blog=blog,
        r2=r2,
        limits=limits,
        report=report,
        database_path=str(raw.get("database_path", "data/news_history.sqlite3")),
    )
