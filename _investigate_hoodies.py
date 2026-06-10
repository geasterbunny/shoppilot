"""Find hoodie blueprints (pullover + zip-up) available via an AU provider, and
their colourways — so we can map Core 4 (Black, Navy, Heather Grey, Cream)."""

import asyncio

from api import printify

AU = {34, 66}
CORE = ["black", "navy", "heather", "cream", "grey", "gray"]


async def main():
    bps = await printify.list_blueprints()
    cands = [b for b in bps if "hoodie" in str(b.get("title", "")).lower()
             or "zip" in str(b.get("title", "")).lower()]
    print(f"{len(cands)} hoodie/zip blueprints in catalog\n")

    for b in cands:
        try:
            provs = await printify.get_print_providers(b["id"])
        except Exception as e:
            continue
        au = [p for p in provs if p.get("id") in AU]
        if not au:
            continue
        title = b.get("title", "")
        kind = "ZIP" if "zip" in title.lower() else "PULLOVER"
        print(f"[{kind}] bp={b['id']} '{title}' AU providers={[(p['id'],p.get('title')) for p in au]}")
        # colours from first AU provider
        try:
            cat = await printify.get_variants(b["id"], au[0]["id"])
            colours = sorted({v["title"].split("/")[0].strip() for v in cat.get("variants", [])})
            core = [c for c in colours if any(k in c.lower() for k in CORE)]
            print(f"      {len(cat.get('variants',[]))} variants | core-ish colours: {core}")
        except Exception as e:
            print(f"      variants err: {str(e)[:60]}")


if __name__ == "__main__":
    asyncio.run(main())
