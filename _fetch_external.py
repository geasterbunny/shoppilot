"""Inspect the Printify `external` field + lock/publish state for ideas 6-10's
products, so we can backfill the real Etsy listing ids."""

import asyncio
import json

import config
from api import printify
from database import Listing, SessionLocal


async def main() -> None:
    shop = config.PRINTIFY_SHOP_ID
    db = SessionLocal()
    try:
        rows = (
            db.query(Listing.idea_id, Listing.printify_product_id)
            .filter(Listing.idea_id.in_([6, 7, 8, 9, 10]))
            .order_by(Listing.idea_id)
            .all()
        )
    finally:
        db.close()

    for idea_id, pid in rows:
        try:
            p = await printify._request("GET", f"/shops/{shop}/products/{pid}.json")
        except Exception as e:
            print(f"idea {idea_id} {pid}: ERROR {e}")
            continue
        print(f"idea {idea_id} {pid}: is_locked={p.get('is_locked')} "
              f"external={json.dumps(p.get('external'))}")


if __name__ == "__main__":
    asyncio.run(main())
