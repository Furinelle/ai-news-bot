from __future__ import annotations

from typing import Any, Callable


PUSHPLUS_SEND_URL = "https://www.pushplus.plus/send"


def build_pushplus_payload(
    token: str,
    title: str,
    content: str,
    channel: str = "clawbot",
    template: str = "markdown",
) -> dict[str, str]:
    return {
        "token": token,
        "title": title,
        "content": content,
        "channel": channel,
        "template": template,
    }


def send_pushplus(
    token: str,
    title: str,
    content: str,
    channel: str = "clawbot",
    template: str = "markdown",
    post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    payload = build_pushplus_payload(
        token=token,
        title=title,
        content=content,
        channel=channel,
        template=template,
    )

    if post is None:
        import httpx

        with httpx.Client(timeout=30) as client:
            response = client.post(PUSHPLUS_SEND_URL, json=payload)
    else:
        response = post(PUSHPLUS_SEND_URL, json=payload, timeout=30)

    response.raise_for_status()
    return response.json()
