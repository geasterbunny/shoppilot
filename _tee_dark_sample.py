"""Validate the dark-shirt (light-ink) variant + inspect tee shirt colours."""

import asyncio

from PIL import Image, ImageDraw

import config
from agents.design_agent import _download_bytes, _ideogram_generate
from api import printify

DARK_PROMPT = (
    "A high-quality vintage screen-print illustration for a DARK t-shirt: a "
    "characterful Australian red kangaroo wearing sunglasses with its arms "
    "crossed, looking unimpressed, with the bold hand-lettered slogan "
    "\"Hop Off I'm Busy\" arched above and below it. CREAM and WHITE linework and "
    "lettering with a warm ochre and rust colour fill, all designed to stand out "
    "on a black shirt. Halftone shading, subtle distressed vintage texture. A "
    "single self-contained graphic fully isolated on a solid pure BLACK "
    "background with a clear empty margin — NO coloured panel, NO box, NO frame, "
    "NO t-shirt shown, NOT a mockup. Spell exactly: Hop Off I'm Busy."
)

SENT = (255, 0, 255)


def remove_bg(src, dst, bg, thresh=70):
    img = Image.open(src).convert("RGB")
    w, h = img.size
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
                 (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        ImageDraw.floodfill(img, seed, SENT, thresh=thresh)
    rgba = img.convert("RGBA")
    rgba.putdata([(r, g, b, 0) if (r, g, b) == SENT else (r, g, b, 255)
                  for (r, g, b, _a) in rgba.getdata()])
    rgba.save(dst)


def mock(design, dst, color):
    shirt = Image.new("RGBA", (1000, 1180), color + (255,))
    d = Image.open(design).convert("RGBA")
    tw = int(shirt.width * 0.52); th = int(d.height * tw / d.width)
    d = d.resize((tw, th))
    shirt.alpha_composite(d, ((shirt.width - tw) // 2, int(shirt.height * 0.20)))
    shirt.convert("RGB").save(dst)


async def main():
    print("=== TEE variants bp5 / provider 34 (shirt colours) ===")
    cat = await printify.get_variants(5, 34)
    colours = sorted({v["title"].split("/")[0].strip() for v in cat.get("variants", [])})
    print("colours:", colours)
    print("count:", len(cat.get("variants", [])))

    url = await _ideogram_generate(DARK_PROMPT, "1x1")
    print("url:", url)
    with open("_sample_dark_raw.png", "wb") as f:
        f.write(await _download_bytes(url))
    remove_bg("_sample_dark_raw.png", "_sample_dark_transparent.png", (0, 0, 0))
    mock("_sample_dark_transparent.png", "_sample_dark_on_black.png", (28, 28, 30))
    print("saved dark sample")


if __name__ == "__main__":
    asyncio.run(main())
