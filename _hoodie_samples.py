"""Generate 10 Australian HOODIE design samples (no products created) so the
user can pick a top 3. Each design uses the illustrated transparent approach,
composited onto a heather-grey hoodie colour for preview."""

import asyncio
import io

from PIL import Image

from agents import design_agent
from agents.idea_agent import _get_client, _parse_ideas

MODEL = "claude-sonnet-4-6"

SYSTEM = """You are a product strategist for an Australian Etsy print-on-demand store.
Generate exactly 10 ORIGINAL Australian-themed HOODIE design ideas — cosy, casual, with
broad appeal for winter, camping, footy, coastal mornings, road trips, the pub, mateship.

Each idea must:
- Have a genuine, funny or warm Australian theme (slang, native animals, places, outdoor/cosy culture)
- Contain a short, punchy SLOGAN wrapped in single quotes inside the title
- Be distinct from each other and from existing tees ("She'll Be Right Mate", "Hop Off I'm Busy", "Powered by Snags & Stubbies")
- Spell every slogan word correctly

Return ONLY a JSON array of exactly 10 objects, each with:
- product_title: format: Australian <theme> Hoodie - '<Slogan>' Cosy Aussie Hoodie <suffix>
- product_type: "hoodie"
- description: 2-sentence friendly Australian description
- target_buyer: one sentence on who buys this

Return only the JSON array, no other text."""


class _Idea:
    def __init__(self, title, ptype):
        self.product_title = title
        self.product_type = ptype


def mock(design_bytes, dst, colour=(150, 152, 150)):
    g = Image.new("RGBA", (1000, 1100), colour + (255,))
    d = Image.open(io.BytesIO(design_bytes)).convert("RGBA")
    tw = int(g.width * 0.5); th = int(d.height * tw / d.width)
    d = d.resize((tw, th))
    g.alpha_composite(d, ((g.width - tw) // 2, int(g.height * 0.22)))
    g.convert("RGB").save(dst)


async def main():
    client = _get_client()
    resp = await client.messages.create(
        model=MODEL, max_tokens=4096, system=SYSTEM,
        messages=[{"role": "user", "content": "Generate the 10 hoodie ideas now."}],
    )
    raw = "".join(b.text for b in resp.content if hasattr(b, "text"))
    ideas = _parse_ideas(raw)
    print(f"generated {len(ideas)} ideas\n")

    for i, idea in enumerate(ideas, 1):
        obj = _Idea(idea.get("product_title", ""), "hoodie")
        light_prompt, _dark, aspect = design_agent._build_garment_prompts(obj)
        try:
            url = await design_agent._ideogram_generate(light_prompt, aspect)
            png = design_agent._remove_background(await design_agent._download_bytes(url))
            mock(png, f"_hoodie{i}.png")
            print(f"{i}. {idea.get('product_title')}")
        except Exception as e:
            print(f"{i}. FAILED: {str(e)[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
