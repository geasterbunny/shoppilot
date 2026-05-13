import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from api import etsy
from database import ResearchProduct

SEARCH_QUERIES = [
    "australian gift funny",
    "aussie personalised gift",
    "australian wall art",
    "australia native animal print",
    "australian slang gift",
    "aussie pet owner",
    "australian dad gift",
    "australia mug funny",
    "funny australian mug",
    "personalised australia gift",
]

STATE_FILE = Path(__file__).resolve().parent.parent / "state.json"


def _load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _next_query() -> str:
    state = _load_state()
    last = state.get("last_query_index", -1)
    idx = (last + 1) % len(SEARCH_QUERIES)
    state["last_query_index"] = idx
    _save_state(state)
    return SEARCH_QUERIES[idx]


def _parse_price(price: Any) -> float:
    if isinstance(price, dict):
        amount = price.get("amount") or 0
        divisor = price.get("divisor") or 100
        try:
            return float(amount) / float(divisor)
        except (TypeError, ZeroDivisionError):
            return 0.0
    if isinstance(price, (int, float)):
        return float(price)
    return 0.0


def _extract_shop_name(listing: dict[str, Any]) -> str | None:
    shop = listing.get("shop")
    if isinstance(shop, dict):
        name = shop.get("shop_name")
        if name:
            return name
    return listing.get("shop_name")


def _score_listing(listing: dict[str, Any]) -> dict[str, Any]:
    listing_id = listing.get("listing_id")
    favourites = int(listing.get("num_favorers") or listing.get("favourites") or 0)
    views = int(listing.get("views") or 0)
    score = (favourites * 0.6) + (views * 0.4)
    tags = listing.get("tags") or []
    return {
        "etsy_listing_id": str(listing_id) if listing_id is not None else "",
        "title": listing.get("title") or "",
        "price": _parse_price(listing.get("price")),
        "favourites": favourites,
        "views": views,
        "score": score,
        "tags": ",".join(tags) if isinstance(tags, list) else str(tags),
        "shop_name": _extract_shop_name(listing),
    }


async def run(db: Session) -> dict[str, Any]:
    """Run one cycle of the research agent.

    Rotates through SEARCH_QUERIES, hits Etsy's listing search, scores each
    result with favourites*0.6 + views*0.4, persists the top 10 to
    research_products (skipping duplicates by etsy_listing_id), and returns a
    summary dict.
    """
    query = _next_query()
    response = await etsy.search_listings(query, limit=25)
    results = response.get("results") or []

    scored = [_score_listing(item) for item in results if item.get("listing_id") is not None]
    scored.sort(key=lambda r: r["score"], reverse=True)
    top = scored[:10]

    saved = 0
    for item in top:
        existing = (
            db.query(ResearchProduct)
            .filter(ResearchProduct.etsy_listing_id == item["etsy_listing_id"])
            .first()
        )
        if existing:
            continue
        db.add(
            ResearchProduct(
                etsy_listing_id=item["etsy_listing_id"],
                title=item["title"],
                price=item["price"],
                favourites=item["favourites"],
                views=item["views"],
                score=item["score"],
                tags=item["tags"],
                shop_name=item["shop_name"],
            )
        )
        saved += 1
    db.commit()

    top_score = top[0]["score"] if top else 0.0

    return {
        "query": query,
        "found": len(results),
        "saved": saved,
        "top_score": top_score,
    }
