from __future__ import annotations

from typing import Any, Callable

from .models import NewsItem
from .render import fix_numbering


class LlmError(RuntimeError):
    pass


SYSTEM_PROMPT = """你是严谨的中文科技日报编辑。
请根据用户提供的候选新闻生成中文日报，英文标题和摘要必须翻译或改写为中文。
硬性规则：
1. 只使用候选新闻中的事实，不得编造公司名、数字、日期、融资金额或发布内容。
2. 普通新闻不要输出裸链接，但每条必须在末尾保留可点击来源名，格式为“（来源：[来源名](原文链接)）”；只有 GitHub Trending 条目可以在正文主标题位置输出 GitHub 仓库链接。
3. 单来源重大新闻必须在来源后标注“未交叉验证”，格式为“（来源：[来源名](原文链接)，未交叉验证）”。
4. 日报头部使用 "# 📡 Furina · 每日科技/AI日报"（Markdown 一级标题）。
5. 输出固定三节，节标题分别是：## 🔥 科技热点 / ## 🤖 AI动态 / ## 📦 GitHub Trending。
6. 每个部分最多输出 15 条：科技热点最多 15 条、AI动态最多 15 条、GitHub Trending最多 15 条；只有某部分候选不足 15 条时，才按实际候选数量输出。
7. 每节内部必须使用 1. 2. 3. 编号，编号从1重新开始；不要使用项目符号或无编号段落。
8. 每条写成1到2句，说明“发生了什么”和“为什么值得看”，控制在120到180个中文字符。
9. 重要词语或关键数字可用 **加粗**。
10. GitHub Trending 只能使用“分类：GitHub Trending”且链接为 github.com 的候选条目；如果候选不足 10 条，就按实际数量输出，绝不能用 Hacker News、博客或普通新闻补位。
11. 科技热点和 AI动态每一条都必须包含“来源：”，禁止省略来源；来源名必须来自候选新闻的“来源”字段，原文链接必须来自候选新闻的“链接”字段。
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


def build_chat_payload(
    model: str,
    items: list[NewsItem],
    date_label: str,
    temperature: float = 0.2,
    thinking_enabled: bool = False,
    reasoning_effort: str = "high",
) -> dict[str, Any]:
    user_prompt = f"""请把以下候选新闻整理成日报。
日报日期：{date_label}
必须原样使用这个日期，不要自行推断、改写或替换日期。

候选新闻：
{_format_items(items)}

请直接输出日报正文，不要解释生成过程。内容要比快讯更耐读，但仍然适合微信消息阅读。
特别注意：科技热点和 AI动态每一条都必须以“（来源：[来源名](原文链接)）”或“（来源：[来源名](原文链接)，未交叉验证）”结尾；不要输出裸 URL。
特别注意：三个部分各最多输出 15 条；只有某部分候选不足 15 条时才少于 15 条。
特别注意：GitHub Trending 节只能放候选新闻中“分类：GitHub Trending”的 GitHub 仓库链接，候选不足时可以少于 15 条。

输出骨架：
# 📡 Furina · 每日科技/AI日报
{date_label}

---

## 🔥 科技热点

1. ...（来源：[来源名](https://example.com/original-article)）
2. ...（来源：[来源名](https://example.com/original-article)，未交叉验证）

## 🤖 AI动态

1. ...（来源：[来源名](https://example.com/original-article)）
2. ...（来源：[来源名](https://example.com/original-article)，未交叉验证）

## 📦 GitHub Trending

1. [用户名/仓库名](https://github.com/用户名/仓库名) ...
"""
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    if thinking_enabled:
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = reasoning_effort
    return payload


def summarize_with_llm(
    base_url: str,
    api_key: str,
    model: str,
    items: list[NewsItem],
    date_label: str,
    temperature: float = 0.2,
    timeout_seconds: float = 180,
    thinking_enabled: bool = False,
    reasoning_effort: str = "high",
    post: Callable[..., Any] | None = None,
) -> str:
    payload = build_chat_payload(
        model=model,
        items=items,
        date_label=date_label,
        temperature=temperature,
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
    )
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if post is None:
        import httpx

        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LlmError(
                f"LLM request timed out after {timeout_seconds:g}s. "
                "Try again, reduce limits.max_report_items, or increase llm.timeout_seconds."
            ) from exc
    else:
        try:
            response = post(url, headers=headers, json=payload, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise LlmError(
                f"LLM request timed out after {timeout_seconds:g}s. "
                "Try again, reduce limits.max_report_items, or increase llm.timeout_seconds."
            ) from exc

    try:
        response.raise_for_status()
    except Exception as exc:
        raise LlmError(f"LLM request failed: {exc}") from exc
    data = response.json()
    return fix_numbering(str(data["choices"][0]["message"]["content"]).strip())
