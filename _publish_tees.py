"""Publish the 10 new tees (ideas 11-20): listing_agent -> backfill Etsy ids
(poll Printify external) + PATCH copy -> marketing_agent."""

import asyncio
import json

import config
from agents import listing_agent, marketing_agent
from agents.listing_agent import _build_etsy_patch
from api import etsy, printify
from database import Listing, MarketingPost, ProductIdea, SessionLocal

IDEAS = list(range(11, 21))
MAX_POLLS = 18
POLL_DELAY = 10.0


async def main() -> None:
    db = SessionLocal()
    try:
        result = await listing_agent.run(db)
        print("[listing]", json.dumps(result, default=str))

        targets = (
            db.query(Listing).filter(Listing.idea_id.in_(IDEAS)).order_by(Listing.idea_id).all()
        )
        pending = {l.idea_id: l.printify_product_id for l in targets if not l.etsy_listing_id}
        resolved = {}
        for attempt in range(1, MAX_POLLS + 1):
            for idea_id, pid in list(pending.items()):
                try:
                    p = await printify._request("GET", f"/shops/{config.PRINTIFY_SHOP_ID}/products/{pid}.json")
                    eid = (p.get("external") or {}).get("id")
                except Exception as e:
                    print(f"  [poll {attempt}] idea {idea_id} err {str(e)[:80]}")
                    continue
                if eid:
                    resolved[idea_id] = eid
                    pending.pop(idea_id, None)
            print(f"  [poll {attempt}] resolved={sorted(resolved)} pending={sorted(pending)}")
            if not pending:
                break
            await asyncio.sleep(POLL_DELAY)

        for lst in targets:
            if lst.idea_id in resolved:
                lst.etsy_listing_id = resolved[lst.idea_id]
        db.commit()

        # PATCH our copy onto each listing (best-effort).
        for lst in targets:
            if not lst.etsy_listing_id:
                continue
            idea = db.get(ProductIdea, lst.idea_id)
            try:
                await etsy.update_listing(config.ETSY_SHOP_ID, lst.etsy_listing_id, _build_etsy_patch(idea))
            except Exception as e:
                print(f"  [patch] idea {lst.idea_id}: WARN {str(e)[:120]}")

        print("[marketing]", json.dumps(await marketing_agent.run(db), default=str)[:300])

        print("\n=== NEW TEE LISTINGS ===")
        for lst in db.query(Listing).filter(Listing.idea_id.in_(IDEAS)).order_by(Listing.idea_id).all():
            print(f"  idea {lst.idea_id}: etsy={lst.etsy_listing_id} "
                  f"https://www.etsy.com/listing/{lst.etsy_listing_id}")
        print("unresolved:", sorted(pending))
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
