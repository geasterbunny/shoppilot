"""Re-call /publish.json on one product and dump the full response.

Goal: understand whether Printify's API publish actually triggers an Etsy
push, or whether we need an additional /publishing_succeeded.json call (or
some sales_channel_properties on create) to close the loop.
"""

from __future__ import annotations

import asyncio
import json
import ssl

import httpx
import truststore

import config

# Use the t-shirt as our test subject (idea 4, blueprint 5, has multiple
# variants so any "missing required field" errors will surface).
TEST_PRODUCT_ID = "6a12df4c0903ee1e830c17a9"

_SSL = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


async def main() -> None:
    url = f"https://api.printify.com/v1/shops/{config.PRINTIFY_SHOP_ID}/products/{TEST_PRODUCT_ID}/publish.json"
    headers = {
        "Authorization": f"Bearer {config.PRINTIFY_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "ShopPilot/1.0",
    }
    body = {"title": True, "description": True, "tags": True, "images": True, "variants": True}
    print(f"POST {url}")
    print(f"body: {json.dumps(body)}\n")
    async with httpx.AsyncClient(timeout=60, verify=_SSL) as c:
        r = await c.post(url, headers=headers, json=body)
    print(f"status: {r.status_code}")
    print(f"headers: {dict(r.headers)}")
    print(f"body:\n{r.text}\n")

    # Now re-fetch the product to see if state changed
    print(f"-- product state after publish call --")
    get_url = f"https://api.printify.com/v1/shops/{config.PRINTIFY_SHOP_ID}/products/{TEST_PRODUCT_ID}.json"
    async with httpx.AsyncClient(timeout=60, verify=_SSL) as c:
        r2 = await c.get(get_url, headers=headers)
    p = r2.json()
    print(f"  is_locked: {p.get('is_locked')}")
    print(f"  external:  {p.get('external')}")
    print(f"  sales_channel_properties: {p.get('sales_channel_properties')}")


if __name__ == "__main__":
    asyncio.run(main())
