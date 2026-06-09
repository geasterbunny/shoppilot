"""Verify the 5 new Etsy listings: state, price, tag count, title."""

import asyncio

import config
from api import etsy
from database import Listing, SessionLocal

IDS = {}


async def main() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(Listing.idea_id, Listing.etsy_listing_id)
            .filter(Listing.idea_id.in_([6, 7, 8, 9, 10]))
            .order_by(Listing.idea_id)
            .all()
        )
    finally:
        db.close()

    for idea_id, lid in rows:
        try:
            l = await etsy.get_listing(lid)
        except Exception as e:
            print(f"idea {idea_id} listing {lid}: GET error {e}")
            continue
        price = l.get("price") or {}
        amt = price.get("amount")
        div = price.get("divisor") or 1
        tags = l.get("tags") or []
        print(f"idea {idea_id} listing {lid}: state={l.get('state')!r} "
              f"price={amt/div if amt else '?'} {price.get('currency_code')} "
              f"tags={len(tags)} url=https://www.etsy.com/listing/{lid}")
        print(f"    title: {l.get('title','')[:70]}")


if __name__ == "__main__":
    asyncio.run(main())
