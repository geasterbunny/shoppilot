"""Step 4: set the Etsy shop title (tagline). GET first to confirm the field
name + current value, then PUT; fall back to PATCH if PUT is rejected."""

import asyncio

import config
from api import etsy

NEW_TITLE = "G'Day Gift Co | Personalised Australian Gifts"


async def main() -> None:
    shop_id = config.ETSY_SHOP_ID
    shop = await etsy.get_shop(shop_id)
    print(f"[before] shop_id={shop.get('shop_id')} shop_name={shop.get('shop_name')!r}")
    print(f"[before] title={shop.get('title')!r}")

    for method in ("PUT", "PATCH"):
        try:
            res = await etsy.update_shop(shop_id, {"title": NEW_TITLE}, method=method)
            print(f"[update] {method} OK")
            print(f"[after] title={res.get('title')!r} shop_name={res.get('shop_name')!r}")
            return
        except Exception as e:
            print(f"[update] {method} failed: {str(e)[:300]}")
    print("[update] both PUT and PATCH failed — see errors above.")


if __name__ == "__main__":
    asyncio.run(main())
