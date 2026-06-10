"""Fix the poster (idea 9): keep only PORTRAIT (Vertical) variants, disable the
LANDSCAPE (Horizontal) ones, restrict print_areas to portrait, then re-publish."""

import asyncio
import json

import config
from api import printify
from database import Listing, SessionLocal

VERTICAL = {81394, 81395, 81396, 81397, 81400, 81401}      # keep (portrait)
HORIZONTAL = {81390, 81391, 81392, 81393, 81398, 81399}    # disable (landscape)


async def main() -> None:
    shop = config.PRINTIFY_SHOP_ID
    db = SessionLocal()
    try:
        pid = (
            db.query(Listing.printify_product_id)
            .filter(Listing.idea_id == 9)
            .scalar()
        )
    finally:
        db.close()

    prod = await printify._request("GET", f"/shops/{shop}/products/{pid}.json")

    # Take the FULL existing variant set and only flip the 6 landscape ones off.
    # Everything else (the already-disabled large sizes) stays exactly as-is, and
    # the existing print_areas (which already covers every variant) is reused
    # unchanged — that keeps Printify's variant/print_areas validation happy.
    new_variants = [
        {
            "id": v["id"],
            "price": v.get("price"),
            "is_enabled": False if v["id"] in HORIZONTAL else v.get("is_enabled", False),
        }
        for v in prod.get("variants", [])
    ]
    new_print_areas = prod.get("print_areas")

    payload = {"variants": new_variants, "print_areas": new_print_areas}
    print("[update] total variants:", len(new_variants),
          "| disabling landscape:", sorted(HORIZONTAL))
    print("[update] keeping portrait enabled:", sorted(VERTICAL))

    await printify._request("PUT", f"/shops/{shop}/products/{pid}.json", json=payload)
    print("[update] PUT OK")

    pub = await printify.publish_product(shop, pid)
    print("[publish] OK:", json.dumps(pub)[:160])

    # Confirm.
    after = await printify._request("GET", f"/shops/{shop}/products/{pid}.json")
    enabled = [v["id"] for v in after.get("variants", []) if v.get("is_enabled")]
    print("[after] enabled variant ids:", enabled)


if __name__ == "__main__":
    asyncio.run(main())
