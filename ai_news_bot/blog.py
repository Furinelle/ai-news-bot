from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BlogPublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class BlogPublishResult:
    feed_id: int
    alias: str
    url: str
    created: bool


def publish_report_to_blog(
    base_url: str,
    username: str,
    password: str,
    report: str,
    slug: str,
    selected_count: int,
    title_prefix: str = "每周科技 / AI 周报",
    tags: tuple[str, ...] | list[str] = ("每周新闻", "AI", "科技"),
    timeout_seconds: float = 30,
    client: Any | None = None,
) -> BlogPublishResult:
    root = base_url.strip().rstrip("/")
    if not root:
        raise BlogPublishError("blog base URL is required")
    if not username or not password:
        raise BlogPublishError("blog credentials are required")

    owns_client = client is None
    if client is None:
        import httpx

        client = httpx.Client(timeout=timeout_seconds)

    alias = f"weekly-news-{slug}"
    public_url = f"{root}/feed/{alias}"
    try:
        login_response = client.post(
            f"{root}/api/auth/login",
            json={"username": username, "password": password},
            timeout=timeout_seconds,
        )
        if login_response.status_code < 200 or login_response.status_code >= 300:
            raise BlogPublishError(f"blog login failed: {_response_detail(login_response)}")
        login_data = _response_json(login_response, "blog login")
        token = str(login_data.get("token", "")).strip()
        if not token:
            raise BlogPublishError("blog login failed: token missing")

        headers = {"Authorization": f"Bearer {token}"}
        create_response = client.post(
            f"{root}/api/feed",
            headers=headers,
            json={
                "title": f"{title_prefix} · {slug}",
                "alias": alias,
                "content": report,
                "summary": f"{slug} 每周科技与 AI 新闻精选，共 {selected_count} 条。",
                "tags": list(tags),
                "listed": True,
                "draft": False,
            },
            timeout=timeout_seconds,
        )
        if 200 <= create_response.status_code < 300:
            create_data = _response_json(create_response, "blog publish")
            return BlogPublishResult(
                feed_id=int(create_data["insertedId"]),
                alias=alias,
                url=public_url,
                created=True,
            )

        if create_response.status_code == 400 and "Content already exists" in _response_detail(create_response):
            existing_response = client.get(
                f"{root}/api/feed/{alias}",
                headers=headers,
                timeout=timeout_seconds,
            )
            if 200 <= existing_response.status_code < 300:
                existing_data = _response_json(existing_response, "existing blog post")
                return BlogPublishResult(
                    feed_id=int(existing_data["id"]),
                    alias=alias,
                    url=public_url,
                    created=False,
                )

        raise BlogPublishError(f"blog publish failed: {_response_detail(create_response)}")
    finally:
        if owns_client:
            client.close()


def _response_json(response: Any, label: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise BlogPublishError(f"{label} returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise BlogPublishError(f"{label} returned invalid JSON")
    return data


def _response_detail(response: Any) -> str:
    text = str(getattr(response, "text", "")).strip()
    if text:
        return text[:300]
    try:
        return str(response.json())[:300]
    except ValueError:
        return f"HTTP {getattr(response, 'status_code', 'unknown')}"
