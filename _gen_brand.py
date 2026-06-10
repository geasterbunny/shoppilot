"""Generate brand assets (shop icon + cover banner) for G'Day Gift Co via the
project's Ideogram integration, save PNGs for manual upload to Etsy."""

import asyncio
import sys

from agents.design_agent import _download_bytes, _ideogram_generate

ICON_PROMPT = (
    "Flat vector logo emblem for an Australian gift shop called \"G'Day Gift Co\". "
    "A clean circular badge: a friendly stylised kangaroo silhouette with a small "
    "gum leaf sprig, and the shop name \"G'Day Gift Co\" in bold rounded retro "
    "lettering curved around the badge. Warm Australian palette — ochre and "
    "terracotta, eucalyptus green, on a cream background. Modern, friendly, high "
    "contrast, centered, isolated on a plain cream background. Flat 2D design, NOT "
    "a photograph, no 3D mockup. Spell the text exactly: G'Day Gift Co."
)

BANNER_PROMPT = (
    "Wide horizontal storefront cover banner for an Australian gift shop. On the "
    "left, the brand name \"G'Day Gift Co\" in bold friendly rounded retro "
    "lettering with the smaller tagline \"Personalised Australian Gifts\" beneath "
    "it. To the right, a hand-illustrated flat row of Australian icons — kangaroo, "
    "gum leaves, boomerang, smiling sun. Warm cream background with ochre, "
    "terracotta, eucalyptus green and sunny yellow. Flat 2D vector illustration, "
    "clean, generous negative space, balanced composition, NOT a photo, no 3D "
    "mockup. Spell exactly: G'Day Gift Co, Personalised Australian Gifts."
)

JOBS = {
    "icon": (ICON_PROMPT, "1x1", "_brand_icon.png"),
    "banner": (BANNER_PROMPT, "16x9", "_brand_banner.png"),
}


async def main() -> None:
    which = sys.argv[1:] or list(JOBS)
    for key in which:
        prompt, aspect, out = JOBS[key]
        url = await _ideogram_generate(prompt, aspect)
        data = await _download_bytes(url)
        with open(out, "wb") as f:
            f.write(data)
        print(f"[{key}] {out} ({len(data)} bytes)  url={url}")


if __name__ == "__main__":
    asyncio.run(main())
