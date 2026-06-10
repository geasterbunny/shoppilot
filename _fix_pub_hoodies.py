"""Backfill Etsy ids for the pub hoodies and correct their titles (the apostrophe
in 'Beer O'Clock' had truncated them)."""

import asyncio

import config
from api import etsy, printify
from database import Listing, ProductIdea, SessionLocal

FIX = {
    "6a292bb926549101eb0661e1": "Australian Pub Afternoon Pullover Hoodie - 'Beer O'Clock, No Dramas' Funny Aussie Pullover Hoodie Gift",
    "6a292bc167f98a3d3e02c7ae": "Australian Pub Afternoon Zip-Up Hoodie - 'Beer O'Clock, No Dramas' Funny Aussie Zip-Up Hoodie Gift",
}


async def main():
    shop = config.PRINTIFY_SHOP_ID
    db = SessionLocal()
    try:
        for pid, title in FIX.items():
            lst = db.query(Listing).filter(Listing.printify_product_id == pid).first()
            idea = db.get(ProductIdea, lst.idea_id)
            # Correct title on Printify + DB, then republish to sync to Etsy.
            await printify._request("PUT", f"/shops/{shop}/products/{pid}.json", json={"title": title})
            await printify.publish_product(shop, pid)
            idea.product_title = title
            db.commit()
            print(f"[{pid}] title fixed + republished")

            # Resolve Etsy id (poll) and PATCH the title directly too.
            eid = lst.etsy_listing_id
            for _ in range(18):
                if eid:
                    break
                p = await printify._request("GET", f"/shops/{shop}/products/{pid}.json")
                eid = (p.get("external") or {}).get("id")
                if not eid:
                    await asyncio.sleep(10)
            if eid:
                lst.etsy_listing_id = eid
                db.commit()
                try:
                    await etsy.update_listing(config.ETSY_SHOP_ID, eid,
                                              {"title": title[:140], "description": idea.description,
                                               "tags": idea.tags})
                except Exception as e:
                    print(f"   etsy PATCH warn: {str(e)[:120]}")
                print(f"   etsy={eid}  https://www.etsy.com/listing/{eid}")
            else:
                print("   etsy id still pending")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
