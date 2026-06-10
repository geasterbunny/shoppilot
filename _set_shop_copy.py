"""Set the API-settable shop copy: announcement + buyer sale (thank-you) message."""

import asyncio

import config
from api import etsy

ANNOUNCEMENT = (
    "G'day and welcome to G'Day Gift Co! \U0001F99C We make personalised, "
    "fair-dinkum Aussie gifts — funny mugs, totes, tees, prints & greeting "
    "cards, designed for Australians and the people who love 'em. Everything is "
    "made to order and printed by Australian print partners. Want a name or "
    "hometown added? Pop it in the personalisation box at checkout. Cheers for "
    "stopping by!"
)

SALE_MESSAGE = (
    "Thanks a million for your order, you absolute legend! \U0001F389 Your G'Day "
    "Gift Co piece is being made to order by our Aussie print partners and will be "
    "on its way before you can say 'strewth'. If anything's not quite right, just "
    "flick us a message and we'll sort it out. — The G'Day Gift Co team"
)


async def main() -> None:
    res = await etsy.update_shop(
        config.ETSY_SHOP_ID,
        {"announcement": ANNOUNCEMENT, "sale_message": SALE_MESSAGE},
        method="PUT",
    )
    print("[updateShop] OK")
    print("  announcement set:", bool(res.get("announcement")))
    print("  sale_message set:", bool(res.get("sale_message")))
    print("  title:", res.get("title"))


if __name__ == "__main__":
    asyncio.run(main())
