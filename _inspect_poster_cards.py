"""Inspect the poster's variants (orientation) + confirm the two card listings."""

import asyncio

import config
from api import printify
from database import Listing, ProductIdea, SessionLocal


async def main() -> None:
    shop = config.PRINTIFY_SHOP_ID
    db = SessionLocal()
    try:
        rows = (
            db.query(Listing.idea_id, ProductIdea.product_type,
                     Listing.printify_product_id, Listing.etsy_listing_id,
                     ProductIdea.product_title)
            .join(ProductIdea, Listing.idea_id == ProductIdea.id)
            .order_by(Listing.idea_id)
            .all()
        )
    finally:
        db.close()

    print("=== ALL LISTINGS ===")
    for idea_id, ptype, pid, eid, title in rows:
        print(f"  idea {idea_id} [{ptype}] printify={pid} etsy={eid} | {title[:40]}")

    # Poster = idea 9.
    poster = next((r for r in rows if r[0] == 9), None)
    if poster:
        pid = poster[2]
        print(f"\n=== POSTER PRODUCT {pid} variants ===")
        p = await printify._request("GET", f"/shops/{shop}/products/{pid}.json")
        for v in p.get("variants", []):
            print(f"  id={v.get('id')} enabled={v.get('is_enabled')} title={v.get('title')!r}")
        print("  print_areas variant_ids:",
              [pa.get("variant_ids") for pa in p.get("print_areas", [])])

    print("\n=== CATALOG variants blueprint 1079 / provider 66 (orientation) ===")
    cat = await printify.get_variants(1079, 66)
    for v in cat.get("variants", []):
        print(f"  id={v.get('id')} title={v.get('title')!r}")


if __name__ == "__main__":
    asyncio.run(main())
