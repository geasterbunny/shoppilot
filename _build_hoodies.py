"""Build hoodie products: 3 chosen designs x 2 styles (pullover + zip-up),
Core-4 colours, dual-ink. Reuses the design agent's dual generation and the
listing agent's colour-split print_areas.

Usage: _build_hoodies.py [design_index ...]   (default: 1 2 3 -> #1, #2, #8)
"""

import asyncio
import json
import sys

import config
from agents import design_agent
from agents.listing_agent import _is_dark_colour, _placeholder, _retail_price_cents, _tags_list
from api import etsy, printify
from database import Listing, ProductIdea, SessionLocal, SupplierProduct

SIZES = {"XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "XXL", "XXXL", "XXS"}


def colour_of(title: str) -> str:
    for part in title.split("/"):
        p = part.strip()
        if p.upper() not in SIZES:
            return p
    return title


# The three chosen sample designs. gen_title drives the illustration (slogan +
# theme), matching what was shown in the sample round.
DESIGNS = {
    1: {
        "gen_title": "Australian Campfire Hoodie - 'Cold Tinnies, Warm Fire' Cosy Aussie Hoodie for Campers",
        "desc": "Cosy up by the fire with this fair-dinkum Aussie campfire hoodie. Soft, warm and made for cold nights, cold tinnies and good yarns. Made to order and printed in Australia.",
        "tags": "australian hoodie,camping hoodie,campfire hoodie,aussie gift,funny hoodie,cold tinnies,camping gift,unisex hoodie,mens hoodie,aussie slang,winter hoodie,beer hoodie,outdoor gift",
    },
    2: {
        "gen_title": "Australian Kookaburra Hoodie - 'Laugh It Off, Mate' Cosy Aussie Hoodie for Nature Lovers",
        "desc": "A cracking hand-illustrated kookaburra to remind you to laugh it off, mate. Warm, soft and unmistakably Australian — a top gift for native-bird lovers. Made to order and printed in Australia.",
        "tags": "kookaburra hoodie,australian hoodie,native bird gift,aussie gift,funny hoodie,bird lover gift,laugh it off,unisex hoodie,aussie slang,winter hoodie,nature hoodie,australiana,kookaburra gift",
    },
    8: {
        "gen_title": "Australian Pub Afternoon Hoodie - 'Beer O'Clock, No Dramas' Cosy Aussie Hoodie for Pub Regulars",
        "desc": "For the legend who reckons it's always beer o'clock and there's never any dramas. A cosy, funny Aussie pub hoodie made for cold arvos at the local. Made to order and printed in Australia.",
        "tags": "beer hoodie,australian hoodie,pub hoodie,funny aussie hoodie,aussie gift,beer oclock,no dramas,unisex hoodie,mens hoodie,aussie slang,dad hoodie,winter hoodie,beer gift",
    },
}

STYLES = [
    {"key": "Pullover Hoodie", "blueprint": 499, "provider": 34, "base_cost": 28,
     "colours": {"Black", "Navy", "Athletic Heather", "White Heather"}},
    {"key": "Zip-Up Hoodie", "blueprint": 66, "provider": 34, "base_cost": 30,
     "colours": {"Black", "Navy", "Sport Grey", "White"}},
]


def seo_title(gen_title: str, style_key: str) -> str:
    after = gen_title.split("-", 1)[1] if "-" in gen_title else gen_title
    first, last = after.find("'"), after.rfind("'")
    slogan = after[first + 1:last] if 0 <= first < last else after.strip()
    theme = gen_title.replace("Australian", "").split("Hoodie")[0].strip(" -")
    return f"Australian {theme} {style_key} - '{slogan}' Funny Aussie {style_key} Gift"[:140]


async def build_style(db, design_key, light_id, dark_id, style):
    meta = DESIGNS[design_key]
    cat = await printify.get_variants(style["blueprint"], style["provider"])
    sel = [v for v in cat.get("variants", []) if colour_of(v["title"]) in style["colours"]]
    if not sel:
        print(f"  [{style['key']}] no matching colours — skip"); return None
    price = _retail_price_cents(style["base_cost"])
    variant_ids = [v["id"] for v in sel]
    variants = [{"id": v["id"], "price": price, "is_enabled": True} for v in sel]
    light_ids = [v["id"] for v in sel if not _is_dark_colour(v["title"])]
    dark_ids = [v["id"] for v in sel if _is_dark_colour(v["title"])]
    print_areas = []
    if light_ids:
        print_areas.append({"variant_ids": light_ids, "placeholders": [_placeholder(light_id, "front")]})
    if dark_ids:
        print_areas.append({"variant_ids": dark_ids, "placeholders": [_placeholder(dark_id, "front")]})

    title = seo_title(meta["gen_title"], style["key"])
    payload = {
        "title": title, "description": meta["desc"],
        "blueprint_id": style["blueprint"], "print_provider_id": style["provider"],
        "variants": variants, "tags": _tags_list(meta["tags"]), "print_areas": print_areas,
    }
    created = await printify.create_product(config.PRINTIFY_SHOP_ID, payload)
    pid = created.get("id")
    real_cost = min((v.get("cost") or 0) for v in created.get("variants", []) if v.get("is_enabled")) if created.get("variants") else None
    print(f"  [{style['key']}] product {pid} | {len(light_ids)} light + {len(dark_ids)} dark variants | price={price/100:.2f} real_base_cost={real_cost}")
    await printify.publish_product(config.PRINTIFY_SHOP_ID, pid)

    # DB rows
    idea = ProductIdea(product_title=title, product_type=style["key"].lower(),
                       description=meta["desc"], tags=meta["tags"],
                       printify_search_term="hoodie", status="approved")
    db.add(idea); db.flush()
    db.add(SupplierProduct(idea_id=idea.id, blueprint_id=style["blueprint"],
                           print_provider_id=style["provider"], provider_name="The Print Bar",
                           variant_ids=json.dumps(variant_ids), base_cost=style["base_cost"],
                           image_id=light_id, image_id_dark=dark_id))
    listing = Listing(idea_id=idea.id, printify_product_id=pid, status="live")
    db.add(listing); db.flush()
    db.commit()
    return listing.id, pid


async def backfill(db, pids):
    """Poll Printify external ids and set etsy_listing_id on the new listings."""
    for _ in range(18):
        remaining = []
        for lid, pid in pids:
            lst = db.get(Listing, lid)
            if lst.etsy_listing_id:
                continue
            p = await printify._request("GET", f"/shops/{config.PRINTIFY_SHOP_ID}/products/{pid}.json")
            eid = (p.get("external") or {}).get("id")
            if eid:
                lst.etsy_listing_id = eid; db.commit()
            else:
                remaining.append((lid, pid))
        if not remaining:
            break
        await asyncio.sleep(10)


async def main():
    want = [int(a) for a in sys.argv[1:]] or [1, 2, 8]
    db = SessionLocal()
    made = []
    try:
        for i, dk in enumerate(want, 1):
            meta = DESIGNS[dk]
            obj = type("I", (), {"id": 9000 + dk, "product_title": meta["gen_title"], "product_type": "hoodie"})()
            print(f"\n=== design #{dk}: {meta['gen_title'][:50]} ===")
            light_id, dark_id, _ = await design_agent._design_for_idea(obj)
            print(f"  designs: light={light_id} dark={dark_id}")
            for style in STYLES:
                res = await build_style(db, dk, light_id, dark_id, style)
                if res:
                    made.append(res)
        print("\n[backfill] resolving Etsy ids...")
        await backfill(db, made)
        print("\n=== NEW HOODIE LISTINGS ===")
        for lid, pid in made:
            lst = db.get(Listing, lid)
            t = db.get(ProductIdea, lst.idea_id).product_title
            print(f"  etsy={lst.etsy_listing_id}  https://www.etsy.com/listing/{lst.etsy_listing_id}  | {t[:55]}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
