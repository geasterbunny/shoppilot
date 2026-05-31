"""Printify API client.

Endpoints used by the rest of ShopPilot:
  - list_blueprints()                              -> catalogue search by product type
  - get_print_providers(blueprint_id)              -> list providers for a blueprint
  - get_variants(blueprint_id, provider_id)        -> list variants + base costs
  - create_product(shop_id, payload)               -> create draft Printify product
  - publish_product(shop_id, product_id, payload)  -> push product to Etsy

When MOCK_PRINTIFY=true the client returns hand-built Australian-provider data
so the rest of the pipeline can be developed and tested end-to-end without a
real Printify API key. Keeps the same shape as the live responses (lists of
dicts with `id`, `title`, `location`, `variants`, etc.).
"""

from __future__ import annotations

import ssl
from typing import Any

import httpx
import truststore

import config

PRINTIFY_API_BASE = "https://api.printify.com/v1"
REQUEST_TIMEOUT = 30.0

# Same Windows-cert workaround as api/etsy.py — see comments there.
_SSL_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


class PrintifyAPIError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Printify API error {status_code}: {body}")


def _auth_headers() -> dict[str, str]:
    if not config.PRINTIFY_API_KEY:
        raise RuntimeError("PRINTIFY_API_KEY is not set in config/.env")
    return {
        "Authorization": f"Bearer {config.PRINTIFY_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "ShopPilot/1.0",
    }


async def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{PRINTIFY_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=_SSL_CONTEXT) as client:
        resp = await client.request(method, url, headers=_auth_headers(), **kwargs)
    if resp.status_code >= 400:
        raise PrintifyAPIError(resp.status_code, resp.text)
    if not resp.content:
        return {}
    return resp.json()


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------
#
# IDs are roughly consistent with what Printify's live catalogue returns, but
# they're not guaranteed to match production. The supplier/listing agents
# treat them as opaque identifiers.

_MOCK_BLUEPRINTS: list[dict[str, Any]] = [
    {"id": 5,   "title": "Unisex Heavy Cotton Tee",   "brand": "Gildan",     "model": "5000",  "type": "t-shirt"},
    {"id": 6,   "title": "Unisex Jersey Short Sleeve Tee", "brand": "Bella+Canvas", "model": "3001", "type": "t-shirt"},
    {"id": 9,   "title": "White Glossy Mug 11oz",     "brand": "Generic",    "model": "MUG11", "type": "mug"},
    {"id": 49,  "title": "Eco Tote Bag",              "brand": "Bagedge",    "model": "BE003", "type": "tote"},
    {"id": 282, "title": "Premium Matte Poster",      "brand": "Generic",    "model": "POST",  "type": "poster"},
    {"id": 384, "title": "Folded Greeting Card",      "brand": "Generic",    "model": "GC5x7", "type": "greeting_card"},
]

# Australian print providers we explicitly support per the spec.
#
# IMPORTANT: the provider IDs here MUST be in supplier_agent.AU_PROVIDER_IDS
# ({34, 66}). That agent detects AU providers by ID alone — it ignores the
# `location` field below because the real per-blueprint providers endpoint
# doesn't return one. If these IDs drift from that set, _is_au() filters every
# provider out and the agent reports "no AU print providers". Keep them aligned.
#   34 = The Print Bar (Teneriffe, QLD)
#   66 = Prima Printing (Noble Park North, VIC)
_AU_PROVIDERS_BY_TYPE: dict[str, list[dict[str, Any]]] = {
    "t-shirt":       [{"id": 34, "title": "The Print Bar",  "location": {"country": "AU"}}],
    "tote":          [{"id": 34, "title": "The Print Bar",  "location": {"country": "AU"}},
                      {"id": 66, "title": "Prima Printing", "location": {"country": "AU"}}],
    "mug":           [{"id": 66, "title": "Prima Printing", "location": {"country": "AU"}}],
    "poster":        [{"id": 66, "title": "Prima Printing", "location": {"country": "AU"}}],
    "greeting_card": [{"id": 66, "title": "Prima Printing", "location": {"country": "AU"}}],
}

# Non-AU providers — included so the AU filter has something to strip out.
_NON_AU_PROVIDERS: list[dict[str, Any]] = [
    {"id": 1,  "title": "SPOKE Custom Products", "location": {"country": "US"}},
    {"id": 28, "title": "Drive Fulfillment",     "location": {"country": "US"}},
]

# Base costs (AUD) by product type — low end of typical Printify pricing.
_MOCK_BASE_COST: dict[str, float] = {
    "t-shirt": 12.50,
    "tote": 9.80,
    "mug": 8.20,
    "poster": 7.10,
    "greeting_card": 3.40,
}


def _blueprint_type(blueprint_id: int) -> str:
    for bp in _MOCK_BLUEPRINTS:
        if bp["id"] == blueprint_id:
            return bp["type"]
    return "t-shirt"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def list_blueprints() -> list[dict[str, Any]]:
    if config.MOCK_PRINTIFY:
        return list(_MOCK_BLUEPRINTS)
    return await _request("GET", "/catalog/blueprints.json")


async def get_print_providers(blueprint_id: int) -> list[dict[str, Any]]:
    if config.MOCK_PRINTIFY:
        product_type = _blueprint_type(blueprint_id)
        return _AU_PROVIDERS_BY_TYPE.get(product_type, []) + _NON_AU_PROVIDERS
    return await _request(
        "GET", f"/catalog/blueprints/{blueprint_id}/print_providers.json"
    )


async def get_variants(blueprint_id: int, provider_id: int) -> dict[str, Any]:
    if config.MOCK_PRINTIFY:
        product_type = _blueprint_type(blueprint_id)
        base = _MOCK_BASE_COST.get(product_type, 10.0)
        # Build a tiny variant set — one or two sizes.
        if product_type == "t-shirt":
            variants = [
                {"id": 12100, "title": "Black / S", "price": int(base * 100), "is_available": True},
                {"id": 12101, "title": "Black / M", "price": int(base * 100), "is_available": True},
                {"id": 12102, "title": "Black / L", "price": int((base + 1) * 100), "is_available": True},
                {"id": 12103, "title": "White / M", "price": int(base * 100), "is_available": True},
            ]
        elif product_type == "tote":
            variants = [
                {"id": 23000, "title": "Natural", "price": int(base * 100), "is_available": True},
                {"id": 23001, "title": "Black",   "price": int(base * 100), "is_available": True},
            ]
        elif product_type == "mug":
            variants = [
                {"id": 33100, "title": "11oz White", "price": int(base * 100), "is_available": True},
            ]
        elif product_type == "poster":
            variants = [
                {"id": 44000, "title": "A4",  "price": int(base * 100), "is_available": True},
                {"id": 44001, "title": "A3",  "price": int((base + 2) * 100), "is_available": True},
            ]
        else:  # greeting_card
            variants = [
                {"id": 55000, "title": "5x7", "price": int(base * 100), "is_available": True},
            ]
        return {"variants": variants}
    return await _request(
        "GET",
        f"/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/variants.json",
    )


# Counter for mock product IDs so repeated calls don't collide.
_mock_product_seq = 0


def _next_mock_id() -> str:
    global _mock_product_seq
    _mock_product_seq += 1
    return f"mock_product_{_mock_product_seq:04d}"


async def create_product(shop_id: str | int, payload: dict[str, Any]) -> dict[str, Any]:
    if config.MOCK_PRINTIFY:
        return {
            "id": _next_mock_id(),
            "shop_id": str(shop_id),
            "title": payload.get("title"),
            "blueprint_id": payload.get("blueprint_id"),
            "print_provider_id": payload.get("print_provider_id"),
            "_mock": True,
        }
    return await _request("POST", f"/shops/{shop_id}/products.json", json=payload)


async def publish_product(
    shop_id: str | int, product_id: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    if config.MOCK_PRINTIFY:
        # Mock an Etsy listing ID — Printify normally returns this asynchronously
        # via a webhook, but we shortcut it for local development.
        return {
            "status": "ok",
            "etsy_listing_id": f"mock_etsy_{product_id}",
            "_mock": True,
        }
    return await _request(
        "POST",
        f"/shops/{shop_id}/products/{product_id}/publish.json",
        json=payload or {"title": True, "description": True, "tags": True, "images": True, "variants": True},
    )
