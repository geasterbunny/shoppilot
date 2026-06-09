"""Design Agent — generate print-ready artwork for each supplier match.

For each SupplierProduct that doesn't yet have an `image_id`, this agent:
  1. Extracts the quoted slogan (if any) from the linked ProductIdea's title
  2. Builds a product-type-specific prompt with composition + style guidance
  3. Generates the design via Ideogram V3 (the SOTA for in-image typography)
  4. Uploads the PNG to Printify's image library (POST /v1/uploads/images.json)
  5. Saves the Printify image_id back to supplier_products.image_id

Why Ideogram and not FLUX.1-schnell:
  FLUX.1-schnell garbles text. ShopPilot's product strategy is text-forward
  Aussie novelty merch ('Nanna's Little Ratbags', 'Bloody Proud to be from
  [City]', etc.) — typography accuracy is non-negotiable. Ideogram costs
  ~$0.08/image but produces crisp, legible, correctly-spelled slogans.

Idempotent — rows that already have an image_id are skipped. Per-row failures
are recorded in `skipped` and never raise.

When MOCK_DESIGN=true the agent stamps a deterministic fake image_id
("mock_image_<idea_id>") without calling either external API.
"""

from __future__ import annotations

import base64
import logging
import re
import ssl
from typing import Any

import httpx
import truststore
from sqlalchemy.orm import Session

import config
from database import ProductIdea, SupplierProduct

logger = logging.getLogger("shoppilot.design_agent")

IDEOGRAM_GENERATE_URL = "https://api.ideogram.ai/v1/ideogram-v3/generate"
PRINTIFY_UPLOAD_URL = "https://api.printify.com/v1/uploads/images.json"
REQUEST_TIMEOUT = 120.0  # Ideogram V3 takes 15-45s; allow headroom.

# Same Windows-cert workaround the rest of the API clients use.
_SSL_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


# ---------------------------------------------------------------------------
# Per-product-type design templates
# ---------------------------------------------------------------------------
#
# Each entry tells the model:
#   composition  — where on the product the design sits (chest print, mug wrap,
#                  poster fill, card cover)
#   style        — aesthetic direction tuned to AU novelty merch
#   aspect_ratio — Ideogram V3 aspect ratio (WIDTHxHEIGHT) for the printable area
#
# Aspect ratios are intentionally coarse — Printify will scale and crop to fit
# each variant. Squares (1x1) cover mugs/tees broadly; portrait (3x4) suits
# posters and cards.

_PRODUCT_TEMPLATES: dict[str, dict[str, str]] = {
    "t-shirt": {
        "composition": (
            "centered chest-print design, isolated artwork on solid white background, "
            "approximately 30cm tall printable area, single self-contained illustration"
        ),
        "style": (
            "bold flat-color illustration with vintage Aussie character, "
            "thick confident outlines, palette of warm earthy tones with one accent color, "
            "screen-print aesthetic, NOT a photograph"
        ),
        "aspect_ratio": "1x1",
    },
    "tshirt": {
        "composition": (
            "centered chest-print design, isolated artwork on solid white background, "
            "approximately 30cm tall printable area, single self-contained illustration"
        ),
        "style": (
            "bold flat-color illustration with vintage Aussie character, "
            "thick confident outlines, palette of warm earthy tones with one accent color, "
            "screen-print aesthetic, NOT a photograph"
        ),
        "aspect_ratio": "1x1",
    },
    "mug": {
        "composition": (
            "flat 2D print-ready graphic on a plain solid white background — NOT a "
            "3D product mockup, NO drawn object or product shape behind or around "
            "the design, just the printable design itself. Large bold slogan text "
            "fills the upper two-thirds, one small simple decorative icon below the "
            "text — NO maps, NO background illustrations, NO additional text labels "
            "anywhere"
        ),
        "style": (
            "bold typographic design with a single simple flat-color Aussie icon accent, "
            "warm Australian colour palette (ochre, eucalyptus green, sky blue), "
            "text is the dominant element — icon is secondary and small"
        ),
        "aspect_ratio": "1x1",
    },
    "tote": {
        "composition": (
            "flat 2D print-ready graphic on a plain solid white background — NOT a "
            "3D product mockup, NO drawn object or product shape, just the printable "
            "design itself: a single bold centered motif, high-contrast and readable "
            "from across a room"
        ),
        "style": (
            "minimalist line-art illustration with one or two solid accent colors, "
            "modern Aussie indie design feel"
        ),
        "aspect_ratio": "1x1",
    },
    "poster": {
        "composition": (
            "portrait poster artwork filling the full frame, edge-to-edge composition "
            "with strong focal point in the upper third, no margin needed"
        ),
        "style": (
            "richly detailed vintage-travel-poster aesthetic with bold typography, "
            "warm Australian palette of terracotta, deep teal, sun yellow, "
            "stylised illustration of landmarks or scenes"
        ),
        "aspect_ratio": "3x4",
    },
    "card": {
        "composition": (
            "portrait greeting-card front cover, design fills the upper two-thirds, "
            "leave the bottom 15% relatively clean for a tagline if present, "
            "solid background color filling the frame"
        ),
        "style": (
            "warm, humorous, hand-illustrated Aussie greeting-card aesthetic, "
            "bold legible typography for the slogan, "
            "saturated playful colours"
        ),
        "aspect_ratio": "3x4",
    },
    "greeting_card": {
        "composition": (
            "portrait greeting-card front cover, design fills the upper two-thirds, "
            "leave the bottom 15% relatively clean for a tagline if present, "
            "solid background color filling the frame"
        ),
        "style": (
            "warm, humorous, hand-illustrated Aussie greeting-card aesthetic, "
            "bold legible typography for the slogan, "
            "saturated playful colours"
        ),
        "aspect_ratio": "3x4",
    },
}

# Used when product_type doesn't match the table above.
_DEFAULT_TEMPLATE: dict[str, str] = {
    "composition": (
        "single centered illustration with solid white background, "
        "print-ready, no bleed-edge details"
    ),
    "style": "bold flat-color illustration with playful character",
    "aspect_ratio": "1x1",
}

# Universal negatives that are always appended to the prompt to reduce common
# generation failures.
_NEGATIVE_GUIDANCE = (
    "Avoid: misspelled text, garbled typography, watermarks, signatures, "
    "stock-photo backgrounds, photorealistic depictions of real people, "
    "additional text beyond the specified slogan, 3D product mockups, and any "
    "depiction of a physical product or object the design sits on — output "
    "ONLY the flat printable design on a plain background."
)


def _normalise_product_type(raw: str | None) -> str:
    """Match the supplier_agent normalisation so the template lookup aligns."""
    if not raw:
        return ""
    return raw.strip().lower().replace(" ", "_").replace("-", "_")


# Personalisation placeholders the idea_agent emits in slogans (e.g. "Strewth
# [Name] It's Too Early" for personalised products). The listing-photo art must
# show a representative SAMPLE value, not the literal bracketed token — the
# buyer supplies their own value at checkout. Known tokens map to a sample;
# unknown [Tokens] are stripped so they never print verbatim.
_SAMPLE_PLACEHOLDERS: dict[str, str] = {
    "name": "Sheila",
    "city": "Brisbane",
    "state": "Queensland",
    "town": "Broome",
    "hometown": "Brisbane",
}


def _fill_placeholders(text: str | None) -> str | None:
    """Replace [Token] placeholders with a sample value (strip if unknown)."""
    if not text or "[" not in text:
        return text

    def _sub(m: "re.Match[str]") -> str:
        key = m.group(1).strip().lower()
        return _SAMPLE_PLACEHOLDERS.get(key, "")

    out = re.sub(r"\[([^\]]+)\]", _sub, text)
    # Tidy doubled spaces / stray spaces before punctuation left by a strip.
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([!?.,])", r"\1", out)
    return out.strip()


def _extract_slogan(title: str | None) -> str | None:
    """Pull the quoted slogan out of an idea title.

    ShopPilot's idea_agent generates titles in two separator styles — the early
    ideas use pipes, the later ones use dashes::
        Some prefix | 'The Slogan Goes Here' | Some suffix
        Some prefix - 'The Slogan Goes Here' Some SEO suffix

    We therefore split on BOTH pipes and dash separators. This is critical: if a
    dash-separated title isn't split, no segment starts with a quote, the slogan
    is missed, and the idea falls through to the non-slogan path — which feeds
    the FULL SEO title (e.g. "...Coffee Mug Gift") to Ideogram as the thing to
    illustrate, so the model literally draws a mug. (That bug shipped product
    shapes into the printable artwork for every dash-titled slogan product.)

    Titles may contain apostrophes inside the slogan ("Nanna's Little Ratbags",
    "Can't Parallel Park"). Taking the body after the opening quote and slicing
    to the LAST apostrophe in the segment handles those — any SEO suffix after
    the closing quote carries no apostrophes in practice.

    Returns None when no quoted slogan is present (e.g. illustrative ideas like
    the scratch-off poster or the native-animal nursery set).
    """
    if not title:
        return None
    # Split on " | ", " - ", " – ", " — " (spaced separators) and bare pipes.
    for segment in re.split(r"\s*\|\s*|\s+[-–—]\s+", title):
        seg = segment.strip()
        if seg.startswith("'"):
            body = seg[1:]
            close = body.rfind("'")
            if close > 0:
                return body[:close].strip()
    return None


def _build_prompt(idea: ProductIdea) -> tuple[str, str]:
    """Compose the Ideogram prompt and return (prompt_text, aspect_ratio)."""
    product_type = _normalise_product_type(idea.product_type)
    # Try exact match first, then loose match (e.g. "t_shirt" → "t-shirt")
    template = (
        _PRODUCT_TEMPLATES.get(product_type)
        or _PRODUCT_TEMPLATES.get(product_type.replace("_", "-"))
        or _DEFAULT_TEMPLATE
    )

    slogan = _fill_placeholders(_extract_slogan(idea.product_title))
    parts: list[str] = []

    # 1. Headline of what we're making
    if slogan:
        word_count = len(slogan.split())
        parts.append(
            f"Flat die-cut sticker design, isolated on a plain empty background "
            f"with nothing else in the frame — no objects, no product, no 3D mockup, "
            f"just the graphic floating on a blank background. "
            f"The ONLY text in the design is this {word_count}-word slogan, "
            f'spelled exactly: "{slogan}". '
            f"Every word must be perfectly spelled — letter-perfect. "
            f"The slogan is the hero of the design, rendered large, bold, and legible."
        )
    else:
        # Use only the first pipe-segment of the title to avoid feeding the full
        # product name (e.g. "Scratch-Off Bucket List Poster | ... | ...") as a
        # visual prompt — only the first segment describes the visual concept.
        short_title = _fill_placeholders((idea.product_title or "").split("|")[0].strip()) or ""
        parts.append(
            f"A {product_type.replace('_', ' ')} design illustrating: "
            f"{short_title or idea.description or 'an Australian-themed product'}."
        )
        # Non-slogan designs are illustration-led. Text-heavy SEO titles
        # ("...Wombat Quokka Echidna Watercolour Wall Art Kids Room Decor")
        # otherwise get rendered AS garbled text labels. Force the subjects to be
        # drawn and cap any text to a short, correctly-spelled heading.
        parts.append(
            "Render every subject as an ILLUSTRATION, not as written words. The "
            "only text allowed is a short heading of at most two words, spelled "
            "exactly and correctly. Do NOT render product keywords, descriptive "
            "phrases, or subject names as text labels."
        )

    # 2. Composition
    parts.append("Composition: " + template["composition"] + ".")

    # 3. Style
    parts.append("Style: " + template["style"] + ".")

    # 4. Contextual extras from the idea's description (kept short — Ideogram
    # rewards concise prompts and a long description can dilute the slogan).
    # Skip description extras for slogan designs — the slogan IS the content.
    if not slogan and idea.description:
        snippet = idea.description.strip().split(".")[0]  # first sentence only
        if snippet and len(snippet) < 200:
            parts.append(f"Theme: {snippet}.")

    # 5. For slogan designs: repeat the slogan one more time before negatives.
    # Ideogram responds well to the critical instruction appearing at both ends
    # of the prompt — it anchors text rendering against prompt dilution.
    if slogan:
        parts.append(
            f'Verify text spells: "{slogan}" — no letter substitutions, no truncation.'
        )

    # 6. Negative guidance
    parts.append(_NEGATIVE_GUIDANCE)

    return " ".join(parts), template["aspect_ratio"]


async def _ideogram_generate(prompt: str, aspect_ratio: str) -> str:
    """Call Ideogram V3 and return the URL of the generated image."""
    if not config.IDEOGRAM_API_KEY:
        raise RuntimeError("IDEOGRAM_API_KEY is not set in config/.env")
    # V3 expects multipart/form-data with flat fields — no `image_request`
    # wrapper and no `model` (the endpoint path selects V3). The (None, value)
    # tuples make httpx emit each field as a plain multipart part and set the
    # boundary Content-Type itself, so we don't set Content-Type by hand.
    form = {
        "prompt": (None, prompt),
        "aspect_ratio": (None, aspect_ratio),
        "magic_prompt": (None, "OFF"),  # AUTO rewrites our prompt and garbles slogan text
        "style_type": (None, "DESIGN"),
    }
    headers = {"Api-Key": config.IDEOGRAM_API_KEY}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=_SSL_CONTEXT) as client:
        resp = await client.post(IDEOGRAM_GENERATE_URL, headers=headers, files=form)
    if resp.status_code >= 400:
        raise RuntimeError(f"Ideogram {resp.status_code}: {resp.text[:500]}")
    data = resp.json().get("data") or []
    if not data or not data[0].get("url"):
        raise RuntimeError(f"Ideogram response missing data[0].url: {resp.text[:500]}")
    return data[0]["url"]


async def _download_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=_SSL_CONTEXT) as client:
        resp = await client.get(url)
    if resp.status_code >= 400:
        raise RuntimeError(f"image download {resp.status_code}: {resp.text[:200]}")
    return resp.content


async def _printify_upload(idea_id: int, image_bytes: bytes) -> str:
    """Upload base64-encoded PNG to Printify's image library, return image id."""
    if not config.PRINTIFY_API_KEY:
        raise RuntimeError("PRINTIFY_API_KEY is not set in config/.env")
    payload = {
        "file_name": f"design_{idea_id}.png",
        "contents": base64.b64encode(image_bytes).decode("ascii"),
    }
    headers = {
        "Authorization": f"Bearer {config.PRINTIFY_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "ShopPilot/1.0",
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=_SSL_CONTEXT) as client:
        resp = await client.post(PRINTIFY_UPLOAD_URL, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"Printify upload {resp.status_code}: {resp.text}")
    image_id = resp.json().get("id")
    if not image_id:
        raise RuntimeError(f"Printify upload returned no id: {resp.text}")
    return image_id


async def _design_for_idea(idea: ProductIdea) -> tuple[str, str | None]:
    """End-to-end: prompt -> Ideogram V3 -> download -> Printify upload.

    Returns (printify_image_id, source_image_url). source_image_url is the
    Ideogram-generated image URL, or None in mock mode where no image is made.
    """
    if config.MOCK_DESIGN:
        return f"mock_image_{idea.id}", None
    prompt, aspect = _build_prompt(idea)
    logger.info("design_agent: idea %s prompt: %s", idea.id, prompt[:200])
    image_url = await _ideogram_generate(prompt, aspect)
    image_bytes = await _download_bytes(image_url)
    image_id = await _printify_upload(idea.id, image_bytes)
    return image_id, image_url


async def run(db: Session) -> dict[str, Any]:
    """Generate + upload artwork for every SupplierProduct missing image_id."""
    pending = (
        db.query(SupplierProduct, ProductIdea)
        .join(ProductIdea, SupplierProduct.idea_id == ProductIdea.id)
        .filter(SupplierProduct.image_id.is_(None))
        .all()
    )

    designed = 0
    products: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for supplier, idea in pending:
        try:
            image_id, image_url = await _design_for_idea(idea)
        except Exception as e:
            logger.exception("design_agent: idea %s failed", idea.id)
            skipped.append({"idea_id": idea.id, "reason": str(e)})
            continue
        supplier.image_id = image_id
        designed += 1
        products.append({
            "idea_id": idea.id,
            "title": idea.product_title,
            "image_id": image_id,
            "image_url": image_url,
        })
    db.commit()

    return {
        "status": "ok",
        "considered": len(pending),
        "designed": designed,
        "products": products,
        "skipped": skipped,
    }
