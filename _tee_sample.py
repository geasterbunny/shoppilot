"""Sample of the improved tee approach: a detailed illustration generated
isolated on white, background knocked out to TRANSPARENT (so only the artwork
prints on the fabric), then composited onto shirt colours for preview."""

import asyncio

from PIL import Image, ImageDraw

from agents.design_agent import _download_bytes, _ideogram_generate

PROMPT = (
    "A high-quality vintage screen-print illustration for a t-shirt: a "
    "characterful Australian red kangaroo wearing sunglasses with its arms "
    "crossed, looking unimpressed, with the bold hand-lettered slogan "
    "\"Hop Off I'm Busy\" arched above and below it. Detailed inky linework, "
    "halftone shading and subtle distressed vintage texture, warm retro palette "
    "of ochre, rust, cream and charcoal. A single self-contained graphic fully "
    "isolated on a plain pure white background with a clear empty margin all "
    "around — NO coloured background panel, NO box, NO frame, NO sticker outline, "
    "NO t-shirt shown, NOT a mockup, NOT a photo. Spell exactly: Hop Off I'm Busy."
)

SENT = (0, 255, 1)  # flood-fill sentinel


def remove_bg(src: str, dst: str, thresh: int = 60) -> None:
    img = Image.open(src).convert("RGB")
    w, h = img.size
    for seed in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
                 (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        ImageDraw.floodfill(img, seed, SENT, thresh=thresh)
    rgba = img.convert("RGBA")
    rgba.putdata([
        (r, g, b, 0) if (r, g, b) == SENT else (r, g, b, 255)
        for (r, g, b, _a) in rgba.getdata()
    ])
    rgba.save(dst)


def mock_on_shirt(design: str, dst: str, color: tuple[int, int, int]) -> None:
    shirt = Image.new("RGBA", (1000, 1180), color + (255,))
    d = Image.open(design).convert("RGBA")
    tw = int(shirt.width * 0.52)
    th = int(d.height * tw / d.width)
    d = d.resize((tw, th))
    shirt.alpha_composite(d, ((shirt.width - tw) // 2, int(shirt.height * 0.20)))
    shirt.convert("RGB").save(dst)


async def main() -> None:
    url = await _ideogram_generate(PROMPT, "1x1")
    print("url:", url)
    raw = await _download_bytes(url)
    with open("_sample_raw.png", "wb") as f:
        f.write(raw)
    remove_bg("_sample_raw.png", "_sample_transparent.png")
    mock_on_shirt("_sample_transparent.png", "_sample_on_white.png", (244, 244, 240))
    mock_on_shirt("_sample_transparent.png", "_sample_on_black.png", (28, 28, 30))
    mock_on_shirt("_sample_transparent.png", "_sample_on_heather.png", (150, 152, 150))
    print("saved: _sample_raw.png _sample_transparent.png _sample_on_white/black/heather.png")


if __name__ == "__main__":
    asyncio.run(main())
