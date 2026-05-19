import base64
import hashlib
import secrets
import ssl
from typing import Any
from urllib.parse import urlencode

import httpx
import truststore

import config

# Python 3.14 on Windows can't find a usable CA bundle through httpx's default
# SSL context (even with certifi installed). truststore.SSLContext binds the
# Windows system trust store instead, which has the CAs Etsy's certs chain to.
# Build it once and reuse it across all httpx clients.
_SSL_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

ETSY_API_BASE = "https://api.etsy.com/v3/application"
ETSY_OAUTH_AUTHORIZE_URL = "https://www.etsy.com/oauth/connect"
ETSY_OAUTH_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

DEFAULT_SCOPES = [
    "listings_r",
    "listings_w",
    "shops_r",
    "shops_w",
    "transactions_r",
]

REQUEST_TIMEOUT = 30.0


class EtsyAPIError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Etsy API error {status_code}: {body}")


def _pkce_pair() -> tuple[str, str]:
    verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    )
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


def generate_auth_url(scopes: list[str] | None = None) -> tuple[str, str]:
    """Build the Etsy OAuth authorization URL.

    Returns (url, code_verifier). The caller must store the code_verifier
    until the OAuth callback fires so it can be used in the token exchange.
    """
    if not config.ETSY_API_KEY:
        raise RuntimeError("ETSY_API_KEY is not set in config/.env")
    if not config.ETSY_REDIRECT_URI:
        raise RuntimeError("ETSY_REDIRECT_URI is not set in config/.env")

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    scope_str = " ".join(scopes or DEFAULT_SCOPES)

    params = {
        "response_type": "code",
        "client_id": config.ETSY_API_KEY,
        "redirect_uri": config.ETSY_REDIRECT_URI,
        "scope": scope_str,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{ETSY_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
    return url, verifier


async def exchange_code_for_tokens(code: str, code_verifier: str) -> dict[str, Any]:
    """Exchange an authorization code for access + refresh tokens."""
    if not config.ETSY_API_KEY:
        raise RuntimeError("ETSY_API_KEY is not set in config/.env")

    payload = {
        "grant_type": "authorization_code",
        "client_id": config.ETSY_API_KEY,
        "redirect_uri": config.ETSY_REDIRECT_URI,
        "code": code,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=_SSL_CONTEXT) as client:
        resp = await client.post(ETSY_OAUTH_TOKEN_URL, data=payload)
    if resp.status_code != 200:
        raise EtsyAPIError(resp.status_code, resp.text)
    return resp.json()


async def refresh_access_token() -> dict[str, Any]:
    """Use the stored refresh token to obtain a new access token."""
    if not config.ETSY_API_KEY:
        raise RuntimeError("ETSY_API_KEY is not set in config/.env")
    if not config.ETSY_REFRESH_TOKEN:
        raise RuntimeError("ETSY_REFRESH_TOKEN is not set in config/.env")

    payload = {
        "grant_type": "refresh_token",
        "client_id": config.ETSY_API_KEY,
        "refresh_token": config.ETSY_REFRESH_TOKEN,
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=_SSL_CONTEXT) as client:
        resp = await client.post(ETSY_OAUTH_TOKEN_URL, data=payload)
    if resp.status_code != 200:
        raise EtsyAPIError(resp.status_code, resp.text)
    return resp.json()


def _auth_headers() -> dict[str, str]:
    # Etsy v3 quirk: the x-api-key header expects the *shared secret*, not the
    # keystring. The keystring is only used as the OAuth client_id. If
    # ETSY_SHARED_SECRET isn't set we fall back to the keystring so existing
    # callers don't break in mock/dev mode, but real API calls will 403.
    api_key = config.ETSY_SHARED_SECRET or config.ETSY_API_KEY
    if not api_key:
        raise RuntimeError("ETSY_API_KEY/ETSY_SHARED_SECRET not set in config/.env")
    if not config.ETSY_ACCESS_TOKEN:
        raise RuntimeError("ETSY_ACCESS_TOKEN is not set in config/.env")
    return {
        "x-api-key": api_key,
        "Authorization": f"Bearer {config.ETSY_ACCESS_TOKEN}",
    }


async def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{ETSY_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=_SSL_CONTEXT) as client:
        resp = await client.request(method, url, headers=_auth_headers(), **kwargs)
    if resp.status_code != 200:
        raise EtsyAPIError(resp.status_code, resp.text)
    return resp.json()


async def get_shop(shop_id: str | int) -> dict[str, Any]:
    return await _request("GET", f"/shops/{shop_id}")


async def get_my_shops() -> dict[str, Any]:
    """Fetch shops owned by the authenticated user.

    The Etsy v3 access token is formatted as `{user_id}.{secret}`, so we can
    derive the user_id locally without needing a separate /users/me lookup.
    """
    if not config.ETSY_ACCESS_TOKEN:
        raise RuntimeError("ETSY_ACCESS_TOKEN is not set in config/.env")
    user_id = config.ETSY_ACCESS_TOKEN.split(".", 1)[0]
    return await _request("GET", f"/users/{user_id}/shops")


_MOCK_LISTINGS: list[dict[str, Any]] = [
    {
        "listing_id": 1001001001,
        "title": "Funny Aussie Mug - 'Maaate' Coffee Mug for Australians",
        "price": {"amount": 2495, "divisor": 100, "currency_code": "AUD"},
        "num_favorers": 487,
        "views": 3210,
        "tags": ["australian", "funny", "mug", "aussie", "gift"],
        "shop": {"shop_name": "DownUnderDesigns"},
    },
    {
        "listing_id": 1001001002,
        "title": "Personalised Kangaroo Wall Art Print - Australian Native Animal Decor",
        "price": {"amount": 3500, "divisor": 100, "currency_code": "AUD"},
        "num_favorers": 312,
        "views": 2104,
        "tags": ["kangaroo", "wall art", "australian", "native animal", "print"],
        "shop": {"shop_name": "OutbackPrintCo"},
    },
    {
        "listing_id": 1001001003,
        "title": "Aussie Pet Portrait - Custom Cattle Dog Watercolour",
        "price": {"amount": 4995, "divisor": 100, "currency_code": "AUD"},
        "num_favorers": 198,
        "views": 1456,
        "tags": ["pet", "australian", "cattle dog", "custom", "watercolour"],
        "shop": {"shop_name": "BushDogStudio"},
    },
    {
        "listing_id": 1001001004,
        "title": "Aussie Slang T-Shirt - 'Heaps Good' Funny Australian Tee",
        "price": {"amount": 2999, "divisor": 100, "currency_code": "AUD"},
        "num_favorers": 256,
        "views": 1890,
        "tags": ["slang", "tshirt", "funny", "australian", "gift"],
        "shop": {"shop_name": "TrueBlueThreads"},
    },
    {
        "listing_id": 1001001005,
        "title": "Australian Dad Father's Day Gift - 'Best Dad in the Outback' Mug",
        "price": {"amount": 2750, "divisor": 100, "currency_code": "AUD"},
        "num_favorers": 421,
        "views": 2876,
        "tags": ["dad", "father's day", "australian", "outback", "mug"],
        "shop": {"shop_name": "OzGiftEmporium"},
    },
]


def _mock_search_listings(query: str, limit: int) -> dict[str, Any]:
    results = _MOCK_LISTINGS[:limit]
    return {"count": len(results), "results": results, "_mock": True, "_query": query}


async def search_listings(query: str, limit: int = 25) -> dict[str, Any]:
    # Mock branch runs first and returns immediately — never falls through to
    # _request() (which would require ETSY_API_KEY + ETSY_ACCESS_TOKEN).
    if config.MOCK_ETSY:
        return _mock_search_listings(query, limit)
    params = {"keywords": query, "limit": limit, "includes": "Images"}
    return await _request("GET", "/listings/active", params=params)


async def get_listing(listing_id: str | int) -> dict[str, Any]:
    return await _request("GET", f"/listings/{listing_id}")


async def update_listing(
    shop_id: str | int, listing_id: str | int, data: dict[str, Any]
) -> dict[str, Any]:
    return await _request(
        "PATCH", f"/shops/{shop_id}/listings/{listing_id}", data=data
    )
