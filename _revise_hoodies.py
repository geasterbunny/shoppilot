"""Revise hoodies: move the print to the BACK only, scale it as large as
possible, and make a BLACK variant the default so the listing/shop thumbnail
shows the black colourway (not white).

Usage: _revise_hoodies.py [printify_product_id ...]   (default: all hoodies)
"""

import asyncio
import sys

import config
from agents.listing_agent import _is_dark_colour, _placeholder
from api import printify
from database import Listing, ProductIdea, SessionLocal, SupplierProduct

POSITION = "back"
SCALE = 1.0


def back_placeholder(image_id):
    return {"position": POSITION,
            "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": SCALE, "angle": 0}]}


async def revise(db, shop, listing):
    idea = db.get(ProductIdea, listing.idea_id)
    sup = db.query(SupplierProduct).filter(SupplierProduct.idea_id == listing.idea_id).first()
    cat = await printify.get_variants(sup.blueprint_id, sup.print_provider_id)
    title_by_id = {v["id"]: v.get("title", "") for v in cat.get("variants", [])}

    prod = await printify._request("GET", f"/shops/{shop}/products/{listing.printify_product_id}.json")

    # Pick a Black variant to be the default mockup colour (prefer an enabled M/L).
    enabled = [v for v in prod.get("variants", []) if v.get("is_enabled")]
    blacks = [v for v in enabled if "black" in title_by_id.get(v["id"], "").lower()]
    def _sz_rank(v):
        t = title_by_id.get(v["id"], "")
        for i, s in enumerate(("/ M", "/ L", " M ", " L ", "M", "L")):
            if s in t:
                return i
        return 99
    default_id = sorted(blacks, key=_sz_rank)[0]["id"] if blacks else (enabled[0]["id"] if enabled else None)

    variants = [{"id": v["id"], "price": v.get("price"), "is_enabled": v.get("is_enabled", False),
                 "is_default": v["id"] == default_id}
                for v in prod.get("variants", [])]

    # Back print_areas covering ALL variants, split by fabric colour.
    light_ids, dark_ids = [], []
    for v in prod.get("variants", []):
        (dark_ids if _is_dark_colour(title_by_id.get(v["id"], "")) else light_ids).append(v["id"])
    print_areas = []
    if light_ids:
        print_areas.append({"variant_ids": light_ids, "placeholders": [back_placeholder(sup.image_id)]})
    if dark_ids:
        print_areas.append({"variant_ids": dark_ids, "placeholders": [back_placeholder(sup.image_id_dark)]})

    await printify._request("PUT", f"/shops/{shop}/products/{listing.printify_product_id}.json",
                            json={"variants": variants, "print_areas": print_areas})
    await printify.publish_product(shop, listing.printify_product_id)
    print(f"  {listing.printify_product_id} | back print scale {SCALE} | default=Black {default_id} | "
          f"{idea.product_title[:45]}")


async def main():
    shop = config.PRINTIFY_SHOP_ID
    db = SessionLocal()
    try:
        want_pids = sys.argv[1:]
        q = (db.query(Listing).join(ProductIdea, Listing.idea_id == ProductIdea.id)
             .filter(ProductIdea.product_type.like("%hoodie%")))
        listings = [l for l in q.all() if (not want_pids or l.printify_product_id in want_pids)]
        print(f"revising {len(listings)} hoodie products")
        for l in listings:
            await revise(db, shop, l)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
