"""Supplier Agent — match approved ideas to an Australian Printify provider.

For each ProductIdea with status='approved' that doesn't yet have a
SupplierProduct row, this agent:
  1. Picks a Printify blueprint matching the idea's product_type
  2. Fetches print providers for that blueprint
  3. Filters to Australian providers (country code 'AU')
  4. Picks the cheapest AU provider by base variant cost
  5. Persists blueprint_id, print_provider_id, variant_ids, base_cost

If no AU provider exists for the product type the idea is skipped (logged in
the return dict so the dashboard / scheduler can surface it). The agent is
idempotent — running it twice doesn't create duplicate rows.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from api import printify
from database import ProductIdea, SupplierProduct

# Map our internal product_type vocabulary to keywords we use to pick a
# Printify blueprint from the catalogue. The keyword is matched against
# blueprint title/type fields; the first match wins. Keep these conservative —
# Aussie POD typically uses these specific blueprints.
PRODUCT_TYPE_TO_BLUEPRINT_KEYWORDS: dict[str, list[str]] = {
    "mug":           ["mug"],
    "tote":          ["tote"],
    "t-shirt":       ["t-shirt", "tee"],
    "tshirt":        ["t-shirt", "tee"],
    "poster":        ["poster"],
    "card":          ["card", "greeting"],
    "greeting_card": ["card", "greeting"],
}


def _normalise_product_type(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.strip().lower().replace(" ", "_")


def _pick_blueprint(product_type: str, blueprints: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the first blueprint whose title or type field matches our keyword list."""
    keywords = PRODUCT_TYPE_TO_BLUEPRINT_KEYWORDS.get(product_type, [])
    if not keywords:
        return None
    for bp in blueprints:
        haystack = " ".join(
            str(bp.get(field, "")).lower() for field in ("title", "type", "brand", "model")
        )
        if any(k in haystack for k in keywords):
            return bp
    return None


def _is_au(provider: dict[str, Any]) -> bool:
    location = provider.get("location") or {}
    country = (location.get("country") or location.get("country_code") or "").upper()
    return country == "AU"


def _min_variant_price(variants: list[dict[str, Any]]) -> float:
    """Printify prices come as integer cents — return AUD float, or inf if empty."""
    available = [v for v in variants if v.get("is_available", True)]
    if not available:
        return float("inf")
    cheapest = min((v.get("price") or 0) for v in available)
    return cheapest / 100.0


async def _resolve_provider_for_idea(idea: ProductIdea) -> dict[str, Any]:
    """Run the catalogue lookup for a single idea and return a result dict.

    Result keys:
      ok                    -> bool
      reason                -> str (when not ok)
      blueprint_id          -> int
      print_provider_id     -> int
      provider_name         -> str
      variant_ids           -> list[int]
      base_cost             -> float
    """
    product_type = _normalise_product_type(idea.product_type)
    blueprints = await printify.list_blueprints()
    blueprint = _pick_blueprint(product_type, blueprints)
    if blueprint is None:
        return {"ok": False, "reason": f"no blueprint match for product_type={product_type!r}"}

    providers = await printify.get_print_providers(blueprint["id"])
    au_providers = [p for p in providers if _is_au(p)]
    if not au_providers:
        return {
            "ok": False,
            "reason": f"no AU print providers for blueprint {blueprint['id']} ({blueprint.get('title')})",
        }

    # For each AU provider fetch variants and compute base cost. Pick the
    # cheapest by base price. Carry forward the variant IDs for the listing
    # agent to use later.
    best: dict[str, Any] | None = None
    for provider in au_providers:
        variants_resp = await printify.get_variants(blueprint["id"], provider["id"])
        variants = variants_resp.get("variants") or []
        if not variants:
            continue
        base = _min_variant_price(variants)
        candidate = {
            "blueprint_id": blueprint["id"],
            "print_provider_id": provider["id"],
            "provider_name": provider.get("title") or provider.get("name") or "Unknown",
            "variant_ids": [v["id"] for v in variants if v.get("is_available", True)],
            "base_cost": base,
        }
        if best is None or candidate["base_cost"] < best["base_cost"]:
            best = candidate

    if best is None:
        return {"ok": False, "reason": "AU providers had no available variants"}

    best["ok"] = True
    return best


async def run(db: Session) -> dict[str, Any]:
    """Process every approved idea that doesn't already have a supplier match."""
    # Subquery — ids of ideas already matched. Avoids re-processing on every run.
    matched_ids = {row[0] for row in db.query(SupplierProduct.idea_id).all()}
    pending = (
        db.query(ProductIdea)
        .filter(ProductIdea.status == "approved")
        .filter(~ProductIdea.id.in_(matched_ids) if matched_ids else True)
        .all()
    )

    matched = 0
    skipped: list[dict[str, Any]] = []
    for idea in pending:
        result = await _resolve_provider_for_idea(idea)
        if not result.get("ok"):
            skipped.append({"idea_id": idea.id, "reason": result.get("reason")})
            continue
        db.add(
            SupplierProduct(
                idea_id=idea.id,
                blueprint_id=result["blueprint_id"],
                print_provider_id=result["print_provider_id"],
                provider_name=result["provider_name"],
                variant_ids=json.dumps(result["variant_ids"]),
                base_cost=result["base_cost"],
            )
        )
        matched += 1
    db.commit()

    return {
        "status": "ok",
        "considered": len(pending),
        "matched": matched,
        "skipped": skipped,
    }
