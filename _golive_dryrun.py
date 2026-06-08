"""Go-live dry-run for ideas 6-10.

1. Delete the stale MOCK rows (supplier_products, listings, marketing_posts)
   for ideas 6-10 so the idempotent agents will re-process them in LIVE mode.
2. Run supplier_agent (live AU provider match) + design_agent (real Ideogram
   images uploaded to Printify).
3. STOP before listing/marketing so the designs can be reviewed first.
"""

import asyncio

import config
from agents import design_agent, supplier_agent
from database import Listing, MarketingPost, ProductIdea, SessionLocal, SupplierProduct

IDEAS = [6, 7, 8, 9, 10]


async def main() -> None:
    print(f"[mocks] ETSY={config.MOCK_ETSY} PRINTIFY={config.MOCK_PRINTIFY} "
          f"POSTIZ={config.MOCK_POSTIZ} DESIGN={config.MOCK_DESIGN}")
    if config.MOCK_PRINTIFY or config.MOCK_DESIGN:
        print("[abort] expected live Printify + Design — flags not flipped. Stopping.")
        return

    db = SessionLocal()
    try:
        # --- 1. Delete stale mock rows for ideas 6-10 -----------------------
        listing_ids = [
            r[0] for r in db.query(Listing.id).filter(Listing.idea_id.in_(IDEAS)).all()
        ]
        m = (
            db.query(MarketingPost)
            .filter(MarketingPost.listing_id.in_(listing_ids))
            .delete(synchronize_session=False)
            if listing_ids else 0
        )
        l = (
            db.query(Listing)
            .filter(Listing.idea_id.in_(IDEAS))
            .delete(synchronize_session=False)
        )
        s = (
            db.query(SupplierProduct)
            .filter(SupplierProduct.idea_id.in_(IDEAS))
            .delete(synchronize_session=False)
        )
        # Make sure the ideas are still 'approved' so supplier_agent picks them up.
        for idea in db.query(ProductIdea).filter(ProductIdea.id.in_(IDEAS)).all():
            idea.status = "approved"
        db.commit()
        print(f"[delete] marketing_posts={m} listings={l} supplier_products={s} "
              f"(for ideas {IDEAS})")

        # --- 2. Supplier match (live, read-only Printify catalog) -----------
        supplier_result = await supplier_agent.run(db)
        print(f"[supplier] {supplier_result}")

        # --- 3. Design (REAL Ideogram + Printify upload) --------------------
        design_result = await design_agent.run(db)
        # Trim the (long) image data for printing; keep the reviewable URLs.
        print(f"[design] status={design_result.get('status')} "
              f"designed={design_result.get('designed')} "
              f"skipped={design_result.get('skipped')}")

        # --- Review summary --------------------------------------------------
        print("\n=== SUPPLIER MATCHES (ideas 6-10) ===")
        for sup, idea in (
            db.query(SupplierProduct, ProductIdea)
            .join(ProductIdea, SupplierProduct.idea_id == ProductIdea.id)
            .filter(SupplierProduct.idea_id.in_(IDEAS))
            .order_by(SupplierProduct.idea_id)
            .all()
        ):
            print(f"  idea {idea.idea_id if hasattr(idea,'idea_id') else idea.id} "
                  f"[{idea.product_type}] bp={sup.blueprint_id} "
                  f"provider={sup.print_provider_id} ({sup.provider_name}) "
                  f"variants={sup.variant_ids} cost=${sup.base_cost} "
                  f"image_id={sup.image_id}")

        print("\n=== DESIGN IMAGE URLS (review these) ===")
        for p in design_result.get("products", []):
            print(f"  idea {p['idea_id']}: {p['title']}")
            print(f"    image_url: {p.get('image_url')}")
            print(f"    printify_image_id: {p.get('image_id')}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
