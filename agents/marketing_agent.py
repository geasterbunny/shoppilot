"""Marketing Agent — schedule social posts for newly-live Etsy listings.

For each Listing with status='live' that has no marketing_posts rows yet:
  1. Look up the underlying ProductIdea for title/description/tags/buyer
  2. Ask Claude for 3 platform-tailored posts (Instagram, Facebook, Pinterest)
  3. Schedule each via postiz.schedule_post() at a staggered time
  4. Persist a MarketingPost row per platform

If the Claude call fails or the JSON is malformed the listing is skipped and
recorded in the return dict so the dashboard / scheduler can surface it. The
agent is idempotent — listings that already have any marketing_posts rows are
not re-processed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.orm import Session

import config
from api import postiz
from database import Listing, MarketingPost, ProductIdea

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
PLATFORMS = ("instagram", "facebook", "pinterest")

# Stagger per-platform send times so the same product doesn't hit every feed
# at once. Tuned for Australian timezones — coarse, refine later.
SCHEDULE_OFFSETS: dict[str, timedelta] = {
    "instagram": timedelta(hours=2),
    "facebook":  timedelta(hours=6),
    "pinterest": timedelta(days=1),
}

SYSTEM_PROMPT = """You are a social-media copywriter for an Australian Etsy
print-on-demand store. Given a newly-live product listing, write three social
posts to promote it — one each for Instagram, Facebook, and Pinterest.

Voice: warm, witty, distinctly Australian. Avoid generic e-commerce phrasing.

Per-platform requirements:
- instagram: 1-2 sentences + 1 line of hashtags (~8-12 hashtags). No URL.
- facebook:  2-3 sentences, conversational, soft call-to-action. May reference the listing.
- pinterest: keyword-rich description (1-2 sentences) optimised for Pinterest search. No hashtags.

Return a JSON array of exactly 3 objects. Each object has:
- platform: one of "instagram", "facebook", "pinterest"
- content:  the post text as a single string

Return only the JSON array, no other text."""


_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in config/.env")
        _client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _format_listing(listing: Listing, idea: ProductIdea) -> str:
    parts = [
        "A new Etsy listing has just gone live. Write the three social posts.",
        "",
        f"Product title: {idea.product_title or '(untitled)'}",
        f"Product type:  {idea.product_type or '(unknown)'}",
        f"Target buyer:  {idea.target_buyer or '(general Aussie audience)'}",
        f"Description:   {idea.description or ''}",
    ]
    if idea.tags:
        parts.append(f"Etsy tags:     {idea.tags}")
    if listing.etsy_listing_id:
        parts.append(f"Etsy listing:  https://www.etsy.com/listing/{listing.etsy_listing_id}")
    return "\n".join(parts)


def _parse_posts(text: str) -> list[dict[str, Any]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON array, got {type(parsed).__name__}")
    return parsed


async def _generate_posts(listing: Listing, idea: ProductIdea) -> list[dict[str, Any]]:
    """Call Claude and return a list of {platform, content} dicts."""
    user_msg = _format_listing(listing, idea)
    client = _get_client()
    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw_text = "".join(b.text for b in response.content if hasattr(b, "text"))
    posts = _parse_posts(raw_text)

    # Normalise — keep only the platforms we care about, dedupe by platform,
    # preserve declared order.
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for p in posts:
        platform = str(p.get("platform", "")).strip().lower()
        content = str(p.get("content", "")).strip()
        if platform not in PLATFORMS or platform in seen or not content:
            continue
        seen.add(platform)
        cleaned.append({"platform": platform, "content": content})
    return cleaned


async def _process_one(
    db: Session, listing: Listing, idea: ProductIdea
) -> dict[str, Any]:
    try:
        posts = await _generate_posts(listing, idea)
    except Exception as e:
        return {"ok": False, "reason": f"claude post generation failed: {e}"}
    if not posts:
        return {"ok": False, "reason": "no valid posts returned by Claude"}

    now = datetime.now(timezone.utc)
    scheduled: list[dict[str, Any]] = []
    for p in posts:
        scheduled_at = now + SCHEDULE_OFFSETS.get(p["platform"], timedelta(hours=2))
        try:
            result = await postiz.schedule_post(
                platform=p["platform"],
                content=p["content"],
                scheduled_at=scheduled_at,
            )
        except Exception as e:
            return {
                "ok": False,
                "reason": f"postiz.schedule_post failed for {p['platform']}: {e}",
                "partial": scheduled,
            }
        db.add(
            MarketingPost(
                listing_id=listing.id,
                platform=p["platform"],
                post_content=p["content"],
                postiz_post_id=str(result.get("id") or ""),
                scheduled_at=scheduled_at,
            )
        )
        scheduled.append({
            "platform": p["platform"],
            "postiz_post_id": result.get("id"),
            "scheduled_at": scheduled_at.isoformat(),
        })
    return {"ok": True, "scheduled": scheduled}


async def run(db: Session) -> dict[str, Any]:
    """Process every live listing that has no marketing posts yet."""
    listings_with_posts = {
        row[0] for row in db.query(MarketingPost.listing_id).distinct().all()
        if row[0] is not None
    }
    pending = (
        db.query(Listing, ProductIdea)
        .join(ProductIdea, Listing.idea_id == ProductIdea.id)
        .filter(Listing.status == "live")
        .filter(~Listing.id.in_(listings_with_posts) if listings_with_posts else True)
        .all()
    )

    processed = 0
    skipped: list[dict[str, Any]] = []
    for listing, idea in pending:
        result = await _process_one(db, listing, idea)
        if not result.get("ok"):
            skipped.append({
                "listing_id": listing.id,
                "idea_id": idea.id,
                "reason": result.get("reason"),
            })
            continue
        processed += 1
    db.commit()

    return {
        "status": "ok",
        "considered": len(pending),
        "processed": processed,
        "skipped": skipped,
    }
