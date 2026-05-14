from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class ScheduleSettings:
    schedule_time: str
    targets: list[str]
    source: str


def normalize_schedule_time(value: str) -> str:
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value or "")
    if not match:
        raise ValueError("时间格式必须是 HH:MM，例如 08:30")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("时间无效，请使用 00:00 到 23:59")
    return f"{hour:02d}:{minute:02d}"


def split_targets(raw: str) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for target in re.split(r"[\n,]+", raw or ""):
        target = target.strip()
        if target and target not in seen:
            targets.append(target)
            seen.add(target)
    return targets


def _saved_targets(saved_state: dict[str, Any] | None, config_targets: str) -> list[str]:
    if saved_state is None:
        return split_targets(config_targets)
    raw_targets = saved_state.get("targets", [])
    if not isinstance(raw_targets, list):
        return []
    targets: list[str] = []
    seen: set[str] = set()
    for target in raw_targets:
        target = str(target).strip()
        if target and target not in seen:
            targets.append(target)
            seen.add(target)
    return targets


def resolve_schedule_settings(
    *,
    config_time: str,
    config_targets: str,
    saved_state: dict[str, Any] | None,
) -> ScheduleSettings:
    if saved_state is None:
        schedule_time = str(config_time or "").strip()
        targets = split_targets(config_targets)
        source = "config"
    else:
        schedule_time = str(saved_state.get("schedule_time") or config_time or "").strip()
        targets = _saved_targets(saved_state, config_targets)
        source = "chat"
    if schedule_time:
        schedule_time = normalize_schedule_time(schedule_time)
    return ScheduleSettings(schedule_time=schedule_time, targets=targets, source=source)


def add_subscription(
    *,
    saved_state: dict[str, Any] | None,
    config_targets: str,
    target: str,
    schedule_time: str,
) -> dict[str, Any]:
    normalized_time = normalize_schedule_time(schedule_time)
    targets = _saved_targets(saved_state, config_targets)
    if target not in targets:
        targets.append(target)
    return {"schedule_time": normalized_time, "targets": targets}


def remove_subscription(
    *,
    saved_state: dict[str, Any] | None,
    config_targets: str,
    target: str,
) -> dict[str, Any]:
    targets = [existing for existing in _saved_targets(saved_state, config_targets) if existing != target]
    schedule_time = ""
    if saved_state is not None:
        schedule_time = str(saved_state.get("schedule_time") or "")
    return {"schedule_time": schedule_time, "targets": targets}
