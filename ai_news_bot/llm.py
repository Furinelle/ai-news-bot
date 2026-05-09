from __future__ import annotations

from typing import Any, Callable

from .models import NewsItem


SYSTEM_PROMPT = """你是严谨的中文科技日报编辑。
请根据用户提供的候选新闻生成中文日报，英文标题和摘要必须翻译或改写为中文。
硬性规则：
1. 只使用候选新闻中的事实，不得编造公司名、数字、日期、融资金额或发布内容。
2. 每条必须保留来源链接。
3. 单来源重大新闻必须标注“未交叉验证”。
4. 输出分为：科技热点、AI动态、GitHub Trending。
5. 每条尽量不超过80个中文字符，风格简洁，适合微信推送。
6. 日报标题使用“📡 Furina · 每日科技/AI日报”。
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
    temperature: float = 0.2,
) -> dict[str, Any]:
    user_prompt = f"""请把以下候选新闻整理成日报。

候选新闻：
{_format_items(items)}

请直接输出日报正文，不要解释生成过程。
"""
    return {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }


def summarize_with_llm(
    base_url: str,
    api_key: str,
    model: str,
    items: list[NewsItem],
    temperature: float = 0.2,
    post: Callable[..., Any] | None = None,
) -> str:
    payload = build_chat_payload(model=model, items=items, temperature=temperature)
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if post is None:
        import httpx

        with httpx.Client(timeout=60) as client:
            response = client.post(url, headers=headers, json=payload)
    else:
        response = post(url, headers=headers, json=payload, timeout=60)

    response.raise_for_status()
    data = response.json()
    return str(data["choices"][0]["message"]["content"]).strip()
