"""Step 3c: run listing_agent LIVE for ideas 6-10, then report in detail.

Scrutinises the print_areas path (the highest-risk part): any
printify.create_product failure surfaces in result['skipped'] with the exact
error text.
"""

import asyncio
import json

import config
from agents import listing_agent
from database import Listing, ProductIdea, SessionLocal


async def main() -> None:
    print(f"[mocks] ETSY={config.MOCK_ETSY} PRINTIFY={config.MOCK_PRINTIFY} "
          f"DESIGN={config.MOCK_DESIGN} POSTIZ={config.MOCK_POSTIZ}")
    if config.MOCK_ETSY or config.MOCK_PRINTIFY:
        print("[abort] expected live Etsy + Printify.")
        return

    db = SessionLocal()
    try:
        result = await listing_agent.run(db)
        print("\n=== listing_agent result ===")
        print(json.dumps(result, indent=2, default=str))

        print("\n=== listings rows for ideas 6-10 ===")
        rows = (
            db.query(Listing, ProductIdea.product_title)
            .join(ProductIdea, Listing.idea_id == ProductIdea.id)
            .filter(Listing.idea_id.in_([6, 7, 8, 9, 10]))
            .order_by(Listing.idea_id)
            .all()
        )
        for lst, title in rows:
            print(f"  idea {lst.idea_id}: printify={lst.printify_product_id} "
                  f"etsy={lst.etsy_listing_id} status={lst.status} | {title[:45]}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
