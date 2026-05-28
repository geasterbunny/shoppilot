"""Verify the uploaded Ideogram images are actually in Printify's image library."""
from __future__ import annotations

import asyncio
import ssl
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import httpx
import truststore

import config

_SSL = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

IMAGE_IDS = [
    "6a1419f14d5df0b0477b800f",
    "6a1419f731359e5c876e5116",
    "6a1419fa53accc0d0794dc87",
    "6a1419ffecb18e5fc5d7a51c",
]

HEADERS = {
    "Authorization": f"Bearer {config.PRINTIFY_API_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "ShopPilot/1.0",
}


async def main() -> None:
    # 1. List recent uploads — returns paginated list of uploaded images
    print("=== GET /v1/uploads.json (first page) ===")
    async with httpx.AsyncClient(timeout=30, verify=_SSL) as c:
        r = await c.get(
            "https://api.printify.com/v1/uploads.json?page=1&limit=20",
            headers=HEADERS,
        )
    print(f"status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        items = data.get("data") or []
        print(f"total uploaded images in library: {data.get('total', '?')}")
        print(f"images on this page: {len(items)}")
        for img in items[:10]:
            print(f"  id={img.get('id')}  file_name={img.get('file_name')!r}  preview_url={img.get('preview_url', '')[:80]}")
    else:
        print(r.text[:500])
    print()

    # 2. Fetch each of our image IDs directly
    print("=== Fetching each image by ID ===")
    async with httpx.AsyncClient(timeout=30, verify=_SSL) as c:
        for img_id in IMAGE_IDS:
            r = await c.get(
                f"https://api.printify.com/v1/uploads/{img_id}.json",
                headers=HEADERS,
            )
            if r.status_code == 200:
                img = r.json()
                print(f"  {img_id}: OK  file_name={img.get('file_name')!r}  size={img.get('size')}  preview_url={img.get('preview_url', '')[:80]}")
            else:
                print(f"  {img_id}: {r.status_code}  {r.text[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
