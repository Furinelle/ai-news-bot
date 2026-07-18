from __future__ import annotations

from typing import Any, Callable


DEFAULT_REMOTE_PUSH_URL = "https://push.scripting.fun/push"


def build_remote_push_payload(
    title: str,
    body: str,
    action: str = "",
    icon: str = "newspaper.fill",
    icon_color: str = "systemBlue",
    sound: str = "default",
) -> dict[str, str]:
    payload = {
        "title": title,
        "body": body,
        "icon": icon,
        "iconColor": icon_color,
        "sound": sound,
    }
    if action:
        payload["action"] = action
    return payload


def send_remote_push(
    api_key: str,
    title: str,
    body: str,
    endpoint: str = DEFAULT_REMOTE_PUSH_URL,
    action: str = "",
    post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    payload = build_remote_push_payload(title=title, body=body, action=action)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if post is None:
        import httpx

        with httpx.Client(timeout=30) as client:
            response = client.post(endpoint, headers=headers, json=payload)
    else:
        response = post(endpoint, headers=headers, json=payload, timeout=30)

    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"ok": True}
