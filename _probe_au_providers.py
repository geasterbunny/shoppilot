"""Probe: scan Printify's live catalogue for AU providers per product type.

For each product_type we care about, walk every matching blueprint (not just
the first) and list which ones have AU print providers, with the cheapest
variant cost. Output gives us the data to decide whether to:
  - Loosen supplier_agent to iterate until AU is found
  - Hard-code blueprint preferences
  - Allow non-AU providers as a fallback
"""

from __future__ import annotations

import asyncio
from typing import Any

from agents.supplier_agent import (
    PRODUCT_TYPE_TO_BLUEPRINT_KEYWORDS,
    _is_au,
    _min_variant_price,
)
from api import printify


async def main() -> None:
    blueprints = await printify.list_blueprints()
    print(f"total blueprints in catalogue: {len(blueprints)}\n")

    for product_type, keywords in PRODUCT_TYPE_TO_BLUEPRINT_KEYWORDS.items():
        if product_type in ("tshirt",):  # alias of t-shirt
            continue
        print(f"=== {product_type} (keywords={keywords}) ===")
        matches: list[dict[str, Any]] = []
        for bp in blueprints:
            haystack = " ".join(
                str(bp.get(f, "")).lower() for f in ("title", "type", "brand", "model")
            )
            if any(k in haystack for k in keywords):
                matches.append(bp)
        print(f"  matching blueprints: {len(matches)}")
        au_found_any = False
        for bp in matches[:25]:  # cap per type so output stays sane
            try:
                providers = await printify.get_print_providers(bp["id"])
            except Exception as e:
                print(f"    bp {bp['id']:>4} ({bp.get('title')}) — providers fetch failed: {e}")
                continue
            au = [p for p in providers if _is_au(p)]
            if not au:
                continue
            au_found_any = True
            for p in au:
                try:
                    vresp = await printify.get_variants(bp["id"], p["id"])
                    variants = vresp.get("variants") or []
                    base = _min_variant_price(variants)
                    available_n = sum(1 for v in variants if v.get("is_available", True))
                except Exception as e:
                    print(f"    bp {bp['id']:>4} ({bp.get('title')}) prov {p['id']} ({p.get('title')}) — variants fail: {e}")
                    continue
                print(
                    f"    bp {bp['id']:>4} ({bp.get('title')[:40]:<40}) "
                    f"prov {p['id']:>4} ({p.get('title')[:25]:<25}) "
                    f"AU  variants={available_n}  base=${base:.2f}"
                )
        if not au_found_any:
            print(f"  >>> NO AU providers across {len(matches)} matching blueprints for {product_type!r}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
