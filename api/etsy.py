import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

import config

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
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
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
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.post(ETSY_OAUTH_TOKEN_URL, data=payload)
    if resp.status_code != 200:
        raise EtsyAPIError(resp.status_code, resp.text)
    return resp.json()


def _auth_headers() -> dict[str, str]:
    if not config.ETSY_API_KEY:
        raise RuntimeError("ETSY_API_KEY is not set in config/.env")
    if not config.ETSY_ACCESS_TOKEN:
        raise RuntimeError("ETSY_ACCESS_TOKEN is not set in config/.env")
    return {
        "x-api-key": config.ETSY_API_KEY,
        "Authorization": f"Bearer {config.ETSY_ACCESS_TOKEN}",
    }


async def _request(method: str, path: str, **kwargs: Any) -> Any:
    url = f"{ETSY_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.request(method, url, headers=_auth_headers(), **kwargs)
    if resp.status_code != 200:
        raise EtsyAPIError(resp.status_code, resp.text)
    return resp.json()


async def get_shop(shop_id: str | int) -> dict[str, Any]:
    return await _request("GET", f"/shops/{shop_id}")


async def search_listings(query: str, limit: int = 25) -> dict[str, Any]:
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
