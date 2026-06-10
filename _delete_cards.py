"""Delete both greeting-card products (ideas 5 & 10): remove the Printify
products (which unpublishes/removes the Etsy listings), then verify the Etsy
listing state, then clean the DB (listings + marketing) and mark the ideas
rejected so they're off the sellable list."""

import asyncio

import config
from api import etsy, printify
from database import Listing, MarketingPost, ProductIdea, SessionLocal

CARD_IDEAS = [5, 10]


async def main() -> None:
    shop = config.PRINTIFY_SHOP_ID
    db = SessionLocal()
    try:
        cards = (
            db.query(Listing.id, Listing.idea_id, Listing.printify_product_id,
                     Listing.etsy_listing_id)
            .filter(Listing.idea_id.in_(CARD_IDEAS))
            .all()
        )
        print("[targets]", [(c.idea_id, c.printify_product_id, c.etsy_listing_id) for c in cards])

        # 1. Delete the Printify products.
        for c in cards:
            try:
                await printify._request("DELETE", f"/shops/{shop}/products/{c.printify_product_id}.json")
                print(f"[printify] deleted product {c.printify_product_id} (idea {c.idea_id})")
            except Exception as e:
                print(f"[printify] delete {c.printify_product_id} failed: {str(e)[:200]}")

        # 2. Verify Etsy listing state; deactivate if still active.
        for c in cards:
            if not c.etsy_listing_id:
                continue
            try:
                l = await etsy.get_listing(c.etsy_listing_id)
                state = l.get("state")
                print(f"[etsy] listing {c.etsy_listing_id} (idea {c.idea_id}) state={state!r}")
                if state == "active":
                    try:
                        await etsy._request(
                            "PATCH",
                            f"/shops/{config.ETSY_SHOP_ID}/listings/{c.etsy_listing_id}",
                            data={"state": "inactive"},
                        )
                        print(f"[etsy] -> deactivated {c.etsy_listing_id}")
                    except Exception as e:
                        print(f"[etsy] deactivate {c.etsy_listing_id} failed: {str(e)[:200]}")
            except Exception as e:
                print(f"[etsy] listing {c.etsy_listing_id}: {str(e)[:160]}")

        # 3. DB cleanup.
        listing_ids = [c.id for c in cards]
        m = (db.query(MarketingPost).filter(MarketingPost.listing_id.in_(listing_ids))
             .delete(synchronize_session=False)) if listing_ids else 0
        l = (db.query(Listing).filter(Listing.idea_id.in_(CARD_IDEAS))
             .delete(synchronize_session=False))
        for idea in db.query(ProductIdea).filter(ProductIdea.id.in_(CARD_IDEAS)).all():
            idea.status = "rejected"
        db.commit()
        print(f"[db] deleted marketing={m} listings={l}; ideas {CARD_IDEAS} -> rejected")

        print("[remaining listings]",
              [r[0] for r in db.query(Listing.idea_id).order_by(Listing.idea_id).all()])
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
