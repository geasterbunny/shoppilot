"""Generate 10 Australian-themed T-SHIRT ideas, approve them, run supplier +
design (real Ideogram), and STOP before publishing for review."""

import asyncio

import config
from agents import design_agent, supplier_agent
from agents.idea_agent import _get_client, _parse_ideas
from database import ProductIdea, SessionLocal, SupplierProduct

MODEL = "claude-sonnet-4-6"

SYSTEM = """You are a product strategist for an Australian Etsy print-on-demand store.
Generate exactly 10 ORIGINAL Australian-themed T-SHIRT product ideas. Every idea is a t-shirt.

Each idea must:
- Have a genuine, funny or heart-felt Australian theme (slang, humour, native animals, states, beach/footy/BBQ culture, mateship)
- Contain a short, punchy SLOGAN wrapped in single quotes inside the title
- Be distinct from each other and from these existing tees (do NOT repeat): "Nanna's Little Ratbags", "Powered by Snags & Stubbies"
- Spell every slogan word correctly

Return ONLY a JSON array of exactly 10 objects, each with:
- product_title: SEO Etsy title, max 140 chars, format: Funny Australian <theme> T-Shirt - '<Slogan>' Aussie Tee Gift <suffix>
- product_type: "t-shirt"
- description: 3-sentence listing description in a friendly Australian voice
- tags: comma-separated string of 13 Etsy tags, EACH 20 characters or fewer
- target_buyer: one sentence on who buys this
- printify_search_term: "t-shirt"

Return only the JSON array, no other text."""

USER = "Generate the 10 Australian t-shirt ideas now, following your system prompt exactly."


async def main() -> None:
    if config.MOCK_DESIGN or config.MOCK_PRINTIFY:
        print("[abort] need live Printify + Design.")
        return

    client = _get_client()
    resp = await client.messages.create(
        model=MODEL, max_tokens=4096, system=SYSTEM,
        messages=[{"role": "user", "content": USER}],
    )
    raw = "".join(b.text for b in resp.content if hasattr(b, "text"))
    ideas = _parse_ideas(raw)
    print(f"[ideas] generated {len(ideas)}")

    db = SessionLocal()
    try:
        new_ids = []
        for idea in ideas:
            row = ProductIdea(
                product_title=idea.get("product_title", ""),
                product_type="t-shirt",  # force — this batch is all tees
                description=idea.get("description", ""),
                tags=idea.get("tags", ""),
                target_buyer=idea.get("target_buyer", ""),
                printify_search_term="t-shirt",
                status="approved",
            )
            db.add(row)
            db.flush()
            new_ids.append(row.id)
        db.commit()
        print(f"[ideas] inserted+approved ids: {new_ids}")

        print("[supplier]", await supplier_agent.run(db))
        design_result = await design_agent.run(db)
        print(f"[design] designed={design_result.get('designed')} skipped={design_result.get('skipped')}")

        print("\n=== REVIEW (new tees) ===")
        for p in design_result.get("products", []):
            print(f"idea {p['idea_id']}: {p['title']}")
            print(f"  url: {p.get('image_url')}")
            print(f"  printify_image_id: {p.get('image_id')}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
