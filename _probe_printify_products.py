"""Inspect the live state of each Printify product we just created.

Etsy shows 0 listings, so the publish-to-Etsy step either didn't fire or
silently failed downstream. Printify keeps the canonical state — let's read
each product's record and see what 'external', 'is_locked', and any error
fields say.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys

# Force UTF-8 stdout so we can print Printify variant titles like 20″x16″
# without crashing on the Windows cp1252 console.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
from api.printify import _request


async def main() -> None:
    # First: what does Printify say this shop is? If sales_channel != "etsy"
    # that's a huge clue — publishes are queued but never go anywhere.
    print("=== Printify shops on this account ===")
    shops = await _request("GET", "/shops.json")
    for s in shops:
        print(f"  id={s.get('id')}  title={s.get('title')!r}  sales_channel={s.get('sales_channel')!r}")
    print()

    conn = sqlite3.connect("shoppilot.db")
    rows = list(conn.execute(
        "SELECT idea_id, printify_product_id FROM listings WHERE printify_product_id IS NOT NULL"
    ))
    shop_id = config.PRINTIFY_SHOP_ID
    for idea_id, product_id in rows:
        print(f"=== idea {idea_id} — Printify product {product_id} ===")
        try:
            p = await _request("GET", f"/shops/{shop_id}/products/{product_id}.json")
        except Exception as e:
            print(f"  fetch failed: {e}")
            print()
            continue
        # Pull the interesting fields
        keep = {
            "id": p.get("id"),
            "title": p.get("title"),
            "blueprint_id": p.get("blueprint_id"),
            "print_provider_id": p.get("print_provider_id"),
            "visible": p.get("visible"),
            "is_locked": p.get("is_locked"),
            "user_id": p.get("user_id"),
            "shop_id": p.get("shop_id"),
            "external": p.get("external"),
            "sales_channel_properties": p.get("sales_channel_properties"),
            "tags_count": len(p.get("tags") or []),
            "variants_count": len(p.get("variants") or []),
            "images_count": len(p.get("images") or []),
            "print_areas_count": len(p.get("print_areas") or []),
        }
        for k, v in keep.items():
            print(f"  {k}: {v}")
        # Show a single variant for sanity
        variants = p.get("variants") or []
        if variants:
            v = variants[0]
            print(f"  first variant: id={v.get('id')} price={v.get('price')} cost={v.get('cost')} is_enabled={v.get('is_enabled')} title={v.get('title')!r}")
        # Surface anything that looks like an error or publish history
        for hint_key in ("error", "errors", "publish_history", "publishing_status", "warnings"):
            if hint_key in p:
                print(f"  {hint_key}: {p[hint_key]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
