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
2. 普通新闻不要输出裸链接，但每条必须在末尾保留可点击来源名，格式为“（来源：[来源名](原文链接)）”；只有 GitHub Trending 与「你可能感兴趣」条目可以在正文主标题位置输出 GitHub 仓库链接。
3. 单来源重大新闻必须在来源后标注“未交叉验证”，格式为“（来源：[来源名](原文链接)，未交叉验证）”。
4. 日报头部使用 "# 📡 Furina · 每日科技/AI日报"（Markdown 一级标题）。
5. 输出固定四节，节标题分别是：## 🔥 科技热点 / ## 🤖 AI动态 / ## 📦 GitHub Trending / ## ⭐ 你可能感兴趣。若「你可能感兴趣」候选为 0 条，可省略该节。
6. 科技热点、AI动态、GitHub Trending 每部分最多输出 15 条；「你可能感兴趣」最多输出 8 条。只有某部分候选不足上限时，才按实际候选数量输出。
7. 每节内部必须使用 1. 2. 3. 编号，编号从1重新开始；不要使用项目符号或无编号段落。
8. 科技热点 / AI动态 / GitHub Trending：每条写成1到2句，说明“发生了什么”和“为什么值得看”，控制在120到180个中文字符。
9. 「你可能感兴趣」：每条必须说明仓库的**一技之长/特色功能**，以及**为什么匹配读者兴趣**；可参考候选摘要里的 topics、语言、★数与“匹配”提示；不得编造 README 里没有的功能；控制在100到160个中文字符。
10. 重要词语或关键数字可用 **加粗**。
11. GitHub Trending 只能使用“分类：GitHub Trending”且链接为 github.com 的候选条目；「你可能感兴趣」只能使用“分类：你可能感兴趣”的候选条目。候选不足时按实际数量输出，绝不能用 Hacker News、博客或普通新闻补位，也绝不能把 Trending 条目挪到兴趣节。
12. 科技热点和 AI动态每一条都必须包含“来源：”，禁止省略来源；来源名必须来自候选新闻的“来源”字段，原文链接必须来自候选新闻的“链接”字段。
"""


def _format_items(items: list[NewsItem]) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        tags = "、".join(item.tags) if item.tags else "无"
        lines.append(
            "\n".join(
                [
                    f"{index}. 标题：{item.title}",
                    f"   分类：{item.category}",
                    f"   来源：{item.source}",
                    f"   链接：{item.url}",
                    f"   摘要：{item.summary or '无'}",
                    f"   标签：{tags}",
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
特别注意：科技热点 / AI动态 / GitHub Trending 各最多 15 条；「你可能感兴趣」最多 8 条；只有候选不足时才少于上限。
特别注意：GitHub Trending 节只能放“分类：GitHub Trending”的仓库；「你可能感兴趣」节只能放“分类：你可能感兴趣”的仓库，且要写清特色功能与兴趣匹配点。

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

## ⭐ 你可能感兴趣

1. [用户名/仓库名](https://github.com/用户名/仓库名) 一技之长……匹配你的……
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
