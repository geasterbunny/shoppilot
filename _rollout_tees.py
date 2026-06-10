"""Roll the dual-ink transparent-design approach onto existing live tees.

For each idea id passed (default 11-20): regenerate the two transparent designs,
update the Printify product's print_areas (white shirts -> dark-ink design,
black shirts -> light-ink design), and republish to Etsy.
"""

import asyncio
import json
import sys

import config
from agents import design_agent
from api import printify
from database import Listing, ProductIdea, SessionLocal, SupplierProduct

IDEAS = [int(a) for a in sys.argv[1:]] or list(range(11, 21))


def _existing_position(product) -> str:
    for pa in product.get("print_areas", []):
        for ph in pa.get("placeholders", []):
            if ph.get("position"):
                return ph["position"]
    return "front"


def build_print_areas(product, title_by_id, light_id, dark_id):
    position = _existing_position(product)
    light_ids, dark_ids = [], []
    for v in product.get("variants", []):
        title = title_by_id.get(v["id"], "").lower()
        (dark_ids if ("black" in title or "dark" in title) else light_ids).append(v["id"])

    def ph(image_id):
        return [{"position": position,
                 "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}]}]

    areas = []
    if light_ids:
        areas.append({"variant_ids": light_ids, "placeholders": ph(light_id)})
    if dark_ids:
        areas.append({"variant_ids": dark_ids, "placeholders": ph(dark_id)})
    return areas, len(light_ids), len(dark_ids)


async def main():
    shop = config.PRINTIFY_SHOP_ID
    db = SessionLocal()
    try:
        for iid in IDEAS:
            idea = db.get(ProductIdea, iid)
            supplier = db.query(SupplierProduct).filter(SupplierProduct.idea_id == iid).first()
            listing = db.query(Listing).filter(Listing.idea_id == iid).first()
            if not (idea and supplier and listing):
                print(f"[idea {iid}] missing idea/supplier/listing — skip")
                continue

            print(f"[idea {iid}] regenerating dual designs: {idea.product_title[:50]}")
            light_id, dark_id, _url = await design_agent._design_for_idea(idea)
            supplier.image_id = light_id
            supplier.image_id_dark = dark_id
            db.commit()
            print(f"  light(white-shirt)={light_id} dark(black-shirt)={dark_id}")

            # Catalog titles for colour classification.
            cat = await printify.get_variants(supplier.blueprint_id, supplier.print_provider_id)
            title_by_id = {v["id"]: v.get("title", "") for v in cat.get("variants", [])}

            prod = await printify._request("GET", f"/shops/{shop}/products/{listing.printify_product_id}.json")
            variants = [{"id": v["id"], "price": v.get("price"), "is_enabled": v.get("is_enabled", False)}
                        for v in prod.get("variants", [])]
            print_areas, nl, nd = build_print_areas(prod, title_by_id, light_id, dark_id)
            print(f"  print_areas: {nl} light-shirt variants, {nd} dark-shirt variants")

            await printify._request("PUT", f"/shops/{shop}/products/{listing.printify_product_id}.json",
                                    json={"variants": variants, "print_areas": print_areas})
            pub = await printify.publish_product(shop, listing.printify_product_id)
            print(f"  PUT+publish OK {json.dumps(pub)[:60]}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
