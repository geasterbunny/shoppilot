import json
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.orm import Session

import config
from database import ProductIdea, ResearchProduct

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are a product strategist for an Australian Etsy print-on-demand store.
Given trending Etsy listings in the Australian niche, generate 5 original
product ideas. Each idea must:
- Have a genuine Australian theme (slang, humour, native animals, states, landmarks)
- Be suitable for print-on-demand (mug, tote, t-shirt, poster, greeting_card)
- Include a personalisation angle where possible
- NOT copy existing listings — differentiate with a unique angle

Return a JSON array of exactly 5 objects, each with these fields:
- product_title: SEO-optimised Etsy title (max 140 chars)
- product_type: one of: mug, tote, t-shirt, poster, greeting_card
- description: 3-sentence listing description in friendly Australian voice
- tags: comma-separated string of exactly 13 Etsy tags
- target_buyer: one sentence describing who buys this
- printify_search_term: keyword to find this product in Printify catalogue

Return only the JSON array, no other text."""


_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in config/.env")
        _client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _format_research(rows: list[ResearchProduct]) -> str:
    lines = ["Here are the current top-trending Australian-themed Etsy listings:", ""]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. Title: {r.title}")
        if r.price is not None:
            lines.append(f"   Price: ${r.price:.2f} AUD")
        lines.append(f"   Favourites: {r.favourites or 0}")
        lines.append(f"   Views: {r.views or 0}")
        lines.append(f"   Score: {(r.score or 0):.1f}")
        if r.shop_name:
            lines.append(f"   Shop: {r.shop_name}")
        if r.tags:
            lines.append(f"   Tags: {r.tags}")
        lines.append("")
    lines.append(
        "Based on these trending listings, generate 5 original product ideas "
        "following the guidelines in your system prompt."
    )
    return "\n".join(lines)


def _parse_ideas(text: str) -> list[dict[str, Any]]:
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
        raise ValueError(
            f"Expected a JSON array of ideas, got {type(parsed).__name__}"
        )
    return parsed


async def run(db: Session) -> dict[str, Any]:
    """Generate product ideas from top-scored research and save them as pending_review."""
    rows = (
        db.query(ResearchProduct)
        .order_by(ResearchProduct.score.desc())
        .limit(10)
        .all()
    )
    if len(rows) < 3:
        return {"status": "skipped", "reason": "not enough research data"}

    user_message = _format_research(rows)
    client = _get_client()
    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = "".join(
        block.text for block in response.content if hasattr(block, "text")
    )
    ideas = _parse_ideas(raw_text)

    for idea in ideas:
        db.add(
            ProductIdea(
                product_title=idea.get("product_title", ""),
                product_type=idea.get("product_type", ""),
                description=idea.get("description", ""),
                tags=idea.get("tags", ""),
                target_buyer=idea.get("target_buyer", ""),
                printify_search_term=idea.get("printify_search_term", ""),
                status="pending_review",
            )
        )
    db.commit()

    return {"status": "ok", "ideas_generated": len(ideas)}
