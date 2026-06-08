"""Ad-hoc: re-approve ideas 6-10 and re-run the full agent pipeline, then
verify /suppliers, /listings, /marketing return populated rows.

Mirrors main._run_approval_pipeline (supplier -> design -> listing -> marketing)
but runs the chain once over all approved ideas, since each agent already
processes the full approved/live set idempotently.
"""

import asyncio

import config
from agents import design_agent, listing_agent, marketing_agent, supplier_agent
from database import ProductIdea, SessionLocal
from main import list_listings, list_marketing_posts, list_suppliers


async def main() -> None:
    print(f"[mocks] ETSY={config.MOCK_ETSY} PRINTIFY={config.MOCK_PRINTIFY} "
          f"POSTIZ={config.MOCK_POSTIZ} DESIGN={config.MOCK_DESIGN}")

    db = SessionLocal()
    try:
        # 1. Re-approve ideas 6-10 (idempotent).
        ideas = (
            db.query(ProductIdea)
            .filter(ProductIdea.id.in_([6, 7, 8, 9, 10]))
            .all()
        )
        for idea in ideas:
            idea.status = "approved"
        db.commit()
        print(f"[approve] set {len(ideas)} ideas (6-10) -> approved")

        # 2. Run the full pipeline.
        print("[pipeline] supplier ->", await supplier_agent.run(db))
        print("[pipeline] design   ->", await design_agent.run(db))
        print("[pipeline] listing  ->", await listing_agent.run(db))
        print("[pipeline] marketing->", await marketing_agent.run(db))

        # 3. Verify the three dashboard endpoints return populated rows.
        suppliers = list_suppliers(db)
        listings = list_listings(db)
        marketing = list_marketing_posts(db)
        print()
        print(f"[verify] /suppliers : {len(suppliers)} rows")
        print(f"[verify] /listings  : {len(listings)} rows")
        print(f"[verify] /marketing : {len(marketing)} rows")

        # Per-idea coverage for ideas 6-10.
        print("\n[coverage] ideas 6-10:")
        for iid in (6, 7, 8, 9, 10):
            s = sum(1 for r in suppliers if r["idea_id"] == iid)
            listing_ids = {r["id"] for r in listings if r["idea_id"] == iid}
            m = sum(1 for r in marketing if r["listing_id"] in listing_ids)
            print(f"  idea {iid}: suppliers={s} listings={len(listing_ids)} marketing={m}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
