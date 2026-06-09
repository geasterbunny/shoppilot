"""Backfill real Etsy listing ids from Printify's `external` field, then PATCH
each Etsy listing with our Claude-authored copy (the step listing_agent skipped
because etsy_listing_id wasn't known yet at publish time)."""

import asyncio

import config
from agents.listing_agent import _build_etsy_patch
from api import etsy, printify
from database import Listing, ProductIdea, SessionLocal

IDEAS = [6, 7, 8, 9, 10]
MAX_POLLS = 12
POLL_DELAY = 10.0


async def _external_id(shop: str, pid: str) -> str | None:
    p = await printify._request("GET", f"/shops/{shop}/products/{pid}.json")
    ext = p.get("external") or {}
    return ext.get("id")


async def main() -> None:
    shop = config.PRINTIFY_SHOP_ID
    db = SessionLocal()
    try:
        targets = (
            db.query(Listing)
            .filter(Listing.idea_id.in_(IDEAS))
            .order_by(Listing.idea_id)
            .all()
        )
        pending = {l.idea_id: l.printify_product_id for l in targets if not l.etsy_listing_id}

        # Poll until every product has an external Etsy id (or we give up).
        resolved: dict[int, str] = {}
        for attempt in range(1, MAX_POLLS + 1):
            for idea_id, pid in list(pending.items()):
                try:
                    eid = await _external_id(shop, pid)
                except Exception as e:
                    print(f"  [poll {attempt}] idea {idea_id}: error {e}")
                    continue
                if eid:
                    resolved[idea_id] = eid
                    pending.pop(idea_id, None)
                    print(f"  [poll {attempt}] idea {idea_id}: etsy {eid}")
            if not pending:
                break
            print(f"  [poll {attempt}] still publishing: ideas {sorted(pending)} — waiting {POLL_DELAY:.0f}s")
            await asyncio.sleep(POLL_DELAY)

        # Persist the resolved ids.
        for lst in targets:
            if lst.idea_id in resolved:
                lst.etsy_listing_id = resolved[lst.idea_id]
        db.commit()
        print(f"\n[backfill] set etsy_listing_id on {len(resolved)} listings; "
              f"unresolved: {sorted(pending)}")

        # PATCH our copy onto each resolved listing (best-effort).
        warnings = []
        for lst in targets:
            if not lst.etsy_listing_id:
                continue
            idea = db.query(ProductIdea).get(lst.idea_id)
            try:
                await etsy.update_listing(
                    config.ETSY_SHOP_ID, lst.etsy_listing_id, _build_etsy_patch(idea)
                )
                print(f"  [patch] idea {lst.idea_id} listing {lst.etsy_listing_id}: copy updated")
            except Exception as e:
                warnings.append((lst.idea_id, str(e)[:200]))
                print(f"  [patch] idea {lst.idea_id} listing {lst.etsy_listing_id}: WARN {str(e)[:200]}")

        print("\n=== FINAL listings 6-10 ===")
        for lst in (
            db.query(Listing).filter(Listing.idea_id.in_(IDEAS)).order_by(Listing.idea_id).all()
        ):
            print(f"  idea {lst.idea_id}: etsy={lst.etsy_listing_id} "
                  f"https://www.etsy.com/listing/{lst.etsy_listing_id}")
        if warnings:
            print(f"\n[warnings] {warnings}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
