"""Postiz API client.

Postiz is a self-hosted social-media scheduler (https://postiz.com). We use it
to schedule Instagram / Facebook / Pinterest posts when a new Etsy listing
goes live.

When MOCK_POSTIZ=true the client returns hand-built responses so the marketing
agent can be developed end-to-end without a real Postiz instance. The shape
mirrors what the live endpoint returns.

The live API surface is intentionally narrow — we only need to schedule a
single post for a single integration. If we ever need multi-image carousels or
threads we'll expand from here.
"""

from __future__ import annotations

import ssl
from datetime import datetime
from typing import Any

import httpx
import truststore

import config

REQUEST_TIMEOUT = 30.0

# Same Windows-cert workaround as api/etsy.py.
_SSL_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


class PostizAPIError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Postiz API error {status_code}: {body}")


def _base_url() -> str:
    base = (config.POSTIZ_URL or "").rstrip("/")
    if not base:
        raise RuntimeError("POSTIZ_URL is not set in config/.env")
    return base


def _auth_headers() -> dict[str, str]:
    if not config.POSTIZ_API_KEY:
        raise RuntimeError("POSTIZ_API_KEY is not set in config/.env")
    return {
        "Authorization": f"Bearer {config.POSTIZ_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "ShopPilot/1.0",
    }


# Counter for mock post IDs so repeated calls don't collide.
_mock_post_seq = 0


def _next_mock_id() -> str:
    global _mock_post_seq
    _mock_post_seq += 1
    return f"mock_post_{_mock_post_seq:04d}"


async def schedule_post(
    platform: str,
    content: str,
    scheduled_at: datetime,
    integration_id: str | None = None,
) -> dict[str, Any]:
    """Schedule a single post on one Postiz integration.

    `platform` is one of "instagram", "facebook", "pinterest". Live Postiz
    keys posts to an integration_id (the connected social account) — in mock
    mode that's irrelevant and we synthesise a fake id per call.
    """
    if config.MOCK_POSTIZ:
        return {
            "id": _next_mock_id(),
            "platform": platform,
            "scheduled_at": scheduled_at.isoformat(),
            "status": "scheduled",
            "_mock": True,
        }

    # Live Postiz payload. The public API expects a list of posts grouped by
    # an integration; one post per call is fine for our flow.
    if not integration_id:
        raise RuntimeError(
            f"integration_id is required for live Postiz schedule_post (platform={platform})"
        )
    payload = {
        "type": "schedule",
        "date": scheduled_at.isoformat(),
        "posts": [
            {
                "integration": {"id": integration_id},
                "value": [{"content": content}],
            }
        ],
    }
    url = f"{_base_url()}/public/v1/posts"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=_SSL_CONTEXT) as client:
        resp = await client.post(url, headers=_auth_headers(), json=payload)
    if resp.status_code >= 400:
        raise PostizAPIError(resp.status_code, resp.text)
    body = resp.json() if resp.content else {}
    # Live Postiz returns a list of created posts — normalise to first post's id.
    posts = body.get("posts") if isinstance(body, dict) else None
    post_id = (posts[0].get("id") if posts else None) or body.get("id")
    return {
        "id": post_id,
        "platform": platform,
        "scheduled_at": scheduled_at.isoformat(),
        "status": "scheduled",
        "raw": body,
    }
