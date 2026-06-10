"""Listing Agent — publish supplier-matched ideas as live Etsy listings.

For each SupplierProduct that doesn't yet have an entry in the listings table:
  1. Build a Printify product payload from the idea + supplier match
  2. Call printify.create_product() to draft the Printify product
  3. Call printify.publish_product() to push it to Etsy via Printify
  4. If Etsy is live (MOCK_ETSY=false) and we have a shop_id, PATCH the Etsy
     listing's tags+description with our Claude-generated copy (Printify
     defaults to its own generic copy on publish — we want our own)
  5. Persist a Listing row with status='live', printify_product_id, etsy_listing_id

If any step fails the agent records the failure in `skipped` and moves on. The
agent is idempotent — running it twice does not republish.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

import config
from api import etsy, printify
from database import Listing, ProductIdea, SupplierProduct

# Retail-pricing markup over Printify's base cost. 2.5× is a conservative POD
# margin once Etsy fees, shipping, and ad spend are factored in.
RETAIL_MARKUP = 2.5


def _tags_list(tag_str: str | None) -> list[str]:
    """Etsy tags come from idea_agent as a comma-separated string.

    Etsy enforces two hard limits: at most 13 tags, each at most 20 characters.
    We drop over-length tags entirely (truncating mid-phrase produces junk like
    "kids room decor aust") rather than letting a single long tag 400 the whole
    listing PATCH with "/tags : cannot be more than 20 characters".
    """
    if not tag_str:
        return []
    tags = [t.strip() for t in tag_str.split(",") if t.strip() and len(t.strip()) <= 20]
    return tags[:13]


def _retail_price_cents(base_cost_aud: float) -> int:
    """Apply markup and snap to .95 for Etsy psychological pricing.

    Returns price in integer cents (Printify variants take cents).
    """
    retail = base_cost_aud * RETAIL_MARKUP
    whole = max(int(retail), 1)
    return whole * 100 + 95  # e.g. $20.95


# Garment colours dark enough to need the light-ink artwork. Checked as
# substrings against the variant title (works regardless of "Colour / Size" vs
# "Size / Colour" ordering). Navy is the important non-obvious one.
_DARK_COLOURS = (
    "black", "navy", "dark", "coal", "charcoal", "forest", "chocolate",
    "maroon", "graphite", "midnight", "indigo", "olive",
)


def _is_dark_colour(title: str) -> bool:
    t = (title or "").lower()
    return any(c in t for c in _DARK_COLOURS)


def _placeholder(image_id: str, position: str) -> dict[str, Any]:
    return {
        "position": position,
        "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}],
    }


async def _build_print_areas(
    supplier: SupplierProduct, variant_ids: list[int]
) -> list[dict[str, Any]]:
    """Build the Printify print_areas for a product.

    - Discovers the placeholder position from the live catalog (correct per
      blueprint — "front" for tees/mugs/posters; cards use "cover", etc.).
    - For garments with BOTH light and dark colourways (supplier.image_id_dark
      set, e.g. t-shirts: Solid White + Solid Black), splits the variants by
      colour and maps the dark-ink design to light shirts and the light-ink
      design to dark shirts — so the artwork reads on every colour. Otherwise a
      single design covers all variants.

    Every variant in `variant_ids` is covered by exactly one print_area entry,
    which Printify requires (it rejects products whose enabled variants aren't
    all present in print_areas.*.variant_ids).

    Returns [] when no design exists yet (mock-mode drafts).
    """
    if not supplier.image_id:
        return []
    try:
        resp = await printify.get_variants(supplier.blueprint_id, supplier.print_provider_id)
    except Exception:
        resp = {}
    by_id = {v.get("id"): v for v in (resp.get("variants") or [])}

    positions: list[str] = []
    for vid in variant_ids:
        for ph in (by_id.get(vid) or {}).get("placeholders") or []:
            pos = ph.get("position")
            if pos and pos not in positions:
                positions.append(pos)
    position = "front" if ("front" in positions or not positions) else positions[0]

    if supplier.image_id_dark:
        light_ids, dark_ids = [], []
        for vid in variant_ids:
            title = (by_id.get(vid) or {}).get("title", "")
            (dark_ids if _is_dark_colour(title) else light_ids).append(vid)
        areas: list[dict[str, Any]] = []
        if light_ids:
            areas.append({"variant_ids": light_ids,
                          "placeholders": [_placeholder(supplier.image_id, position)]})
        if dark_ids:
            areas.append({"variant_ids": dark_ids,
                          "placeholders": [_placeholder(supplier.image_id_dark, position)]})
        return areas

    return [{"variant_ids": variant_ids,
             "placeholders": [_placeholder(supplier.image_id, position)]}]


async def _build_printify_payload(idea: ProductIdea, supplier: SupplierProduct) -> dict[str, Any]:
    try:
        variant_ids = json.loads(supplier.variant_ids or "[]")
    except json.JSONDecodeError:
        variant_ids = []
    price_cents = _retail_price_cents(supplier.base_cost or 0.0)
    variants = [
        {"id": vid, "price": price_cents, "is_enabled": True}
        for vid in variant_ids
    ]
    print_areas = await _build_print_areas(supplier, variant_ids)
    return {
        "title": idea.product_title or "",
        "description": idea.description or "",
        "blueprint_id": supplier.blueprint_id,
        "print_provider_id": supplier.print_provider_id,
        "variants": variants,
        "tags": _tags_list(idea.tags),
        "print_areas": print_areas,
    }


def _build_etsy_patch(idea: ProductIdea) -> dict[str, Any]:
    """The PATCH body for updating an Etsy listing's copy."""
    tags = _tags_list(idea.tags)
    return {
        "title": (idea.product_title or "")[:140],
        "description": idea.description or "",
        "tags": ",".join(tags),
    }


async def _publish_one(
    idea: ProductIdea, supplier: SupplierProduct
) -> dict[str, Any]:
    """Run the create → publish → patch flow for a single supplier match."""
    printify_shop_id = config.PRINTIFY_SHOP_ID or "mock_shop"
    payload = await _build_printify_payload(idea, supplier)

    try:
        created = await printify.create_product(printify_shop_id, payload)
    except Exception as e:
        return {"ok": False, "reason": f"printify.create_product failed: {e}"}

    printify_product_id = created.get("id")
    if not printify_product_id:
        return {"ok": False, "reason": "printify.create_product returned no id"}

    try:
        published = await printify.publish_product(
            printify_shop_id, printify_product_id
        )
    except Exception as e:
        return {
            "ok": False,
            "reason": f"printify.publish_product failed: {e}",
            "printify_product_id": printify_product_id,
        }

    etsy_listing_id = published.get("etsy_listing_id")

    # Override Printify's default tags/description with our Claude-authored
    # copy. Skip in mock mode — there's no real Etsy listing to patch.
    if not config.MOCK_ETSY and etsy_listing_id and config.ETSY_SHOP_ID:
        try:
            await etsy.update_listing(
                config.ETSY_SHOP_ID, etsy_listing_id, _build_etsy_patch(idea)
            )
        except Exception as e:
            # Don't fail the whole listing if the patch fails — the product is
            # already live on Etsy with Printify's defaults. Log and continue.
            return {
                "ok": True,
                "printify_product_id": printify_product_id,
                "etsy_listing_id": etsy_listing_id,
                "warning": f"etsy.update_listing failed: {e}",
            }

    return {
        "ok": True,
        "printify_product_id": printify_product_id,
        "etsy_listing_id": etsy_listing_id,
    }


async def run(db: Session) -> dict[str, Any]:
    """Process every supplier match that doesn't already have a live listing."""
    listed_supplier_idea_ids = {
        row[0] for row in db.query(Listing.idea_id).all() if row[0] is not None
    }

    pending = (
        db.query(SupplierProduct, ProductIdea)
        .join(ProductIdea, SupplierProduct.idea_id == ProductIdea.id)
        # Only publish APPROVED ideas. Without this, a rejected/discontinued idea
        # that still has a SupplierProduct row (e.g. a deleted card whose supplier
        # row was left behind) gets republished on the next run — its listing was
        # removed, so it looks "unlisted" and silently comes back to life.
        .filter(ProductIdea.status == "approved")
        .filter(~SupplierProduct.idea_id.in_(listed_supplier_idea_ids)
                if listed_supplier_idea_ids else True)
        .all()
    )

    published = 0
    skipped: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for supplier, idea in pending:
        result = await _publish_one(idea, supplier)
        if not result.get("ok"):
            skipped.append({
                "idea_id": idea.id,
                "supplier_id": supplier.id,
                "reason": result.get("reason"),
            })
            continue
        if result.get("warning"):
            warnings.append({
                "idea_id": idea.id,
                "supplier_id": supplier.id,
                "warning": result["warning"],
            })
        db.add(
            Listing(
                idea_id=idea.id,
                printify_product_id=result.get("printify_product_id"),
                etsy_listing_id=result.get("etsy_listing_id"),
                status="live",
                published_at=datetime.now(timezone.utc),
            )
        )
        published += 1
    db.commit()

    return {
        "status": "ok",
        "considered": len(pending),
        "published": published,
        "skipped": skipped,
        "warnings": warnings,
    }
