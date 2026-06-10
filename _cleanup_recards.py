"""Remove the cards that got republished by the listing_agent bug. This time
also delete their SupplierProduct rows so they can never be recreated."""

import asyncio

import config
from api import etsy, printify
from database import Listing, MarketingPost, ProductIdea, SessionLocal, SupplierProduct

CARD_IDEAS = [5, 10]


async def main() -> None:
    shop = config.PRINTIFY_SHOP_ID
    db = SessionLocal()
    try:
        rows = (
            db.query(Listing.id, Listing.idea_id, Listing.printify_product_id)
            .filter(Listing.idea_id.in_(CARD_IDEAS))
            .all()
        )
        print("[targets]", [(r.idea_id, r.printify_product_id) for r in rows])

        for r in rows:
            # Capture any Etsy id Printify already created, then delete the product.
            eid = None
            try:
                p = await printify._request("GET", f"/shops/{shop}/products/{r.printify_product_id}.json")
                eid = (p.get("external") or {}).get("id")
            except Exception as e:
                print(f"  [get] {r.printify_product_id}: {str(e)[:80]}")
            try:
                await printify._request("DELETE", f"/shops/{shop}/products/{r.printify_product_id}.json")
                print(f"  [printify] deleted {r.printify_product_id} (idea {r.idea_id}); etsy was {eid}")
            except Exception as e:
                print(f"  [printify] delete {r.printify_product_id} failed: {str(e)[:120]}")
            if eid:
                try:
                    l = await etsy.get_listing(eid)
                    if l.get("state") == "active":
                        await etsy._request("PATCH", f"/shops/{config.ETSY_SHOP_ID}/listings/{eid}",
                                            data={"state": "inactive"})
                        print(f"  [etsy] deactivated lingering listing {eid}")
                except Exception as e:
                    print(f"  [etsy] {eid}: {str(e)[:80]} (expected 404 if removed)")

        listing_ids = [r.id for r in rows]
        m = (db.query(MarketingPost).filter(MarketingPost.listing_id.in_(listing_ids))
             .delete(synchronize_session=False)) if listing_ids else 0
        l = db.query(Listing).filter(Listing.idea_id.in_(CARD_IDEAS)).delete(synchronize_session=False)
        s = db.query(SupplierProduct).filter(SupplierProduct.idea_id.in_(CARD_IDEAS)).delete(synchronize_session=False)
        for idea in db.query(ProductIdea).filter(ProductIdea.id.in_(CARD_IDEAS)).all():
            idea.status = "rejected"
        db.commit()
        print(f"[db] deleted marketing={m} listings={l} suppliers={s}; ideas {CARD_IDEAS} -> rejected")

        print("[remaining listing idea_ids]",
              [r[0] for r in db.query(Listing.idea_id).order_by(Listing.idea_id).all()])
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
