"""Auth probe — figure out what Etsy actually wants in x-api-key.

Runs four tests:
  A. /openapi-ping with x-api-key = keystring
  B. /openapi-ping with x-api-key = shared_secret
  C. /users/{id}/shops with x-api-key = keystring + Authorization bearer
  D. /users/{id}/shops with x-api-key = shared_secret + Authorization bearer

/openapi-ping only checks x-api-key (no OAuth) — whichever value gets a 200
is definitively the right thing for x-api-key. Then C/D tell us whether the
full authenticated flow has any additional issue.

Doesn't modify .env, doesn't refresh tokens. Pure read-only.
"""

from __future__ import annotations

import asyncio
import ssl

import httpx
import truststore

import config

ETSY_API_BASE = "https://api.etsy.com/v3/application"
_SSL_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


async def probe(label: str, path: str, headers: dict[str, str]) -> None:
    url = f"{ETSY_API_BASE}{path}"
    masked = {
        k: (f"{v[:6]}...{v[-4:]} (len={len(v)})" if len(v) > 12 else f"{v} (len={len(v)})")
        for k, v in headers.items()
    }
    print(f"--- {label}")
    print(f"  GET {url}")
    print(f"  headers: {masked}")
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=_SSL_CONTEXT) as client:
            resp = await client.get(url, headers=headers)
        body = resp.text[:300]
        print(f"  -> {resp.status_code}  {body}")
    except Exception as e:
        print(f"  -> EXCEPTION: {type(e).__name__}: {e}")
    print()


async def main() -> None:
    keystring = config.ETSY_API_KEY
    shared = config.ETSY_SHARED_SECRET
    token = config.ETSY_ACCESS_TOKEN
    user_id = token.split(".", 1)[0] if token else "?"

    print(f"keystring     = {keystring[:6]}...{keystring[-4:]} (len={len(keystring)})")
    print(f"shared_secret = {shared!r} (len={len(shared)})")
    print(f"access_token  = {token[:8]}...{token[-4:]} (len={len(token)})")
    print(f"derived user  = {user_id}")
    print()

    # A: /openapi-ping with keystring
    await probe(
        "A: /openapi-ping, x-api-key=keystring",
        "/openapi-ping",
        {"x-api-key": keystring},
    )
    # B: /openapi-ping with shared secret
    await probe(
        "B: /openapi-ping, x-api-key=shared_secret",
        "/openapi-ping",
        {"x-api-key": shared},
    )
    # C: /users/{id}/shops with keystring + bearer
    await probe(
        "C: /users/{id}/shops, x-api-key=keystring + Bearer",
        f"/users/{user_id}/shops",
        {"x-api-key": keystring, "Authorization": f"Bearer {token}"},
    )
    # D: /users/{id}/shops with shared secret + bearer
    await probe(
        "D: /users/{id}/shops, x-api-key=shared_secret + Bearer",
        f"/users/{user_id}/shops",
        {"x-api-key": shared, "Authorization": f"Bearer {token}"},
    )


if __name__ == "__main__":
    asyncio.run(main())
