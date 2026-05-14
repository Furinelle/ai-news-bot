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


@dataclass(frozen=True)
class PushplusConfig:
    token: str
    channel: str = "clawbot"
    template: str = "markdown"


@dataclass(frozen=True)
class LimitsConfig:
    max_items: int = 30
    max_report_items: int = 30


@dataclass(frozen=True)
class AppConfig:
    llm: LlmConfig
    pushplus: PushplusConfig
    limits: LimitsConfig
    database_path: str = "data/news_history.sqlite3"


def _required_env(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {env_name}")
    return value


def _read_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config(path: str | Path) -> AppConfig:
    raw = _read_json(path)
    llm_raw = raw.get("llm", {})
    push_raw = raw.get("pushplus", {})
    limits_raw = raw.get("limits", {})

    llm = LlmConfig(
        base_url=str(llm_raw.get("base_url", "")).rstrip("/"),
        api_key=_required_env(str(llm_raw.get("api_key_env", "LLM_API_KEY"))),
        model=str(llm_raw.get("model", "")).strip(),
        temperature=float(llm_raw.get("temperature", 0.2)),
        timeout_seconds=float(llm_raw.get("timeout_seconds", 180)),
    )
    if not llm.base_url:
        raise ConfigError("llm.base_url is required")
    if not llm.model:
        raise ConfigError("llm.model is required")

    pushplus = PushplusConfig(
        token=_required_env(str(push_raw.get("token_env", "PUSHPLUS_TOKEN"))),
        channel=str(push_raw.get("channel", "clawbot")),
        template=str(push_raw.get("template", "markdown")),
    )

    limits = LimitsConfig(
        max_items=int(limits_raw.get("max_items", 30)),
        max_report_items=int(limits_raw.get("max_report_items", 30)),
    )

    return AppConfig(
        llm=llm,
        pushplus=pushplus,
        limits=limits,
        database_path=str(raw.get("database_path", "data/news_history.sqlite3")),
    )
