"""Regenerate designs for ideas 6 (placeholder fix) and 9 (re-roll) only."""

import asyncio
import sys

import config
from agents import design_agent
from database import ProductIdea, SessionLocal, SupplierProduct

REGEN = [int(a) for a in sys.argv[1:]] or [6, 9]


async def main() -> None:
    if config.MOCK_DESIGN:
        print("[abort] MOCK_DESIGN is true — would not generate real images.")
        return
    db = SessionLocal()
    try:
        # Null image_id so design_agent (image_id IS NULL filter) reprocesses them.
        n = (
            db.query(SupplierProduct)
            .filter(SupplierProduct.idea_id.in_(REGEN))
            .update({SupplierProduct.image_id: None}, synchronize_session=False)
        )
        db.commit()
        print(f"[reset] nulled image_id on {n} supplier rows (ideas {REGEN})")

        result = await design_agent.run(db)
        print(f"[design] status={result.get('status')} designed={result.get('designed')} "
              f"skipped={result.get('skipped')}")
        for p in result.get("products", []):
            print(f"  idea {p['idea_id']}: {p['title']}")
            print(f"    image_url: {p.get('image_url')}")
            print(f"    printify_image_id: {p.get('image_id')}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
