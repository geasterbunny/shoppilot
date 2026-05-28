"""One-off: refresh supplier_products with real Printify catalog IDs.

Background: the existing supplier_products rows were created while
MOCK_PRINTIFY=true, so blueprint_id, print_provider_id, variant_ids and
base_cost were all picked from api/printify.py's _MOCK_BLUEPRINTS table.
Now that MOCK_PRINTIFY=false, listing_agent.run() hits Printify with those
fake IDs and gets 404/400 back.

This script:
  - Iterates every supplier_products row joined with its product_idea
  - Calls supplier_agent._resolve_provider_for_idea() — same function used
    in the live pipeline, which now queries the REAL Printify catalog
  - UPDATEs blueprint_id / print_provider_id / provider_name / variant_ids /
    base_cost in place
  - Leaves image_id alone (those uploads are already valid in the Printify
    library and we don't want to burn another HF round trip)

Idempotent — run again if any row still looks wrong.
"""

from __future__ import annotations

import asyncio
import json

from agents import supplier_agent
from database import ProductIdea, SessionLocal, SupplierProduct


async def main() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(SupplierProduct, ProductIdea)
            .join(ProductIdea, SupplierProduct.idea_id == ProductIdea.id)
            .order_by(SupplierProduct.idea_id)
            .all()
        )
        print(f"reseeding {len(rows)} supplier_products row(s) against live Printify catalog\n")
        for supplier, idea in rows:
            print(f"--- idea {idea.id} ({idea.product_type}) — sp id={supplier.id} ---")
            print(f"  BEFORE  blueprint={supplier.blueprint_id}  provider={supplier.print_provider_id}  variants={supplier.variant_ids}  base={supplier.base_cost}")
            try:
                result = await supplier_agent._resolve_provider_for_idea(idea)
            except Exception as e:
                print(f"  ERROR   resolver crashed: {e!r}")
                continue
            if not result.get("ok"):
                print(f"  SKIP    {result.get('reason')}")
                continue
            supplier.blueprint_id = result["blueprint_id"]
            supplier.print_provider_id = result["print_provider_id"]
            supplier.provider_name = result["provider_name"]
            supplier.variant_ids = json.dumps(result["variant_ids"])
            supplier.base_cost = result["base_cost"]
            print(
                f"  AFTER   blueprint={supplier.blueprint_id}  provider={supplier.print_provider_id} "
                f"({supplier.provider_name})  variants={supplier.variant_ids}  base={supplier.base_cost}"
            )
            print(f"  KEEP    image_id={supplier.image_id}")
        db.commit()
        print("\nreseed committed.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
