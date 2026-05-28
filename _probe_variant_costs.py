"""Find out where Printify hides the variant cost.

The catalog variants endpoint returns dimensions/options but maybe not price.
Pricing might come from a separate endpoint, or the same endpoint with a
'cost' field we're not reading. Dump a few raw variants from each of our
4 chosen (blueprint, provider) pairs to see.
"""

from __future__ import annotations

import asyncio
import json

from api.printify import _request

PAIRS = [
    (930, 66),    # mug — Magic Mug, Prima
    (1079, 66),   # poster — Unframed Posters, Prima
    (5, 34),      # t-shirt — Unisex Cotton Crew Tee, The Print Bar
    (962, 66),    # greeting card — Greeting Cards, Prima
]


async def main() -> None:
    for bp_id, prov_id in PAIRS:
        print(f"=== bp {bp_id} / provider {prov_id} ===")
        resp = await _request(
            "GET", f"/catalog/blueprints/{bp_id}/print_providers/{prov_id}/variants.json"
        )
        variants = resp.get("variants") or []
        print(f"  top-level keys: {list(resp.keys())}")
        print(f"  variant count: {len(variants)}")
        if variants:
            v = variants[0]
            print(f"  first variant keys: {list(v.keys())}")
            print(f"  first variant: {json.dumps(v, default=str)[:400]}")
        print()
        # Try the shipping endpoint too — Printify documents costs there sometimes
        try:
            ship = await _request(
                "GET", f"/catalog/blueprints/{bp_id}/print_providers/{prov_id}/shipping.json"
            )
            print(f"  shipping endpoint keys: {list(ship.keys())}")
            print(f"  shipping sample: {json.dumps(ship, default=str)[:300]}")
        except Exception as e:
            print(f"  shipping endpoint failed: {e}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
