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

# Printify provider IDs that are physically located in Australia. Discovered
# via /v1/catalog/print_providers.json — the per-blueprint providers endpoint
# we call elsewhere returns a lightweight shape WITHOUT a location field, so
# we can't rely on provider["location"]["country"] there. Hard-coding the
# small set of AU provider IDs is the only reliable signal for that endpoint.
#  - 34 = The Print Bar (Teneriffe, QLD) — apparel-heavy (tees, hoodies, totes)
#  - 66 = Prima Printing (Noble Park North, VIC) — homewares, cards, posters, mugs
AU_PROVIDER_IDS: set[int] = {34, 66}

# Approximate base costs (AUD) per product type. Used as a floor when the
# catalog variants endpoint doesn't expose a price — which is always, because
# Printify's /catalog/.../variants.json returns only id/title/options/
# placeholders/decoration_methods. There is no documented public catalog
# endpoint that returns provider base cost; the real number only surfaces on
# the create-product response. These values are conservative estimates for AU
# POD pricing and exist so listing_agent doesn't accidentally publish at the
# $1.95 floor. Tune them once you've seen what Printify charges on a real
# product (Printify dashboard > catalog OR your first /shops/.../products.json
# create response).
_DEFAULT_BASE_COST_AUD: dict[str, float] = {
    "mug":           9.00,
    "tote":         13.00,
    "t-shirt":      18.00,
    "tshirt":       18.00,
    "poster":       11.00,
    "card":          4.50,
    "greeting_card": 4.50,
}


def _normalise_product_type(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.strip().lower().replace(" ", "_")


def _matching_blueprints(product_type: str, blueprints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return EVERY blueprint whose title/type/brand/model matches our keyword list.

    Returning a list (not just the first) lets the resolver iterate until it
    finds a blueprint that's actually producible in AU — many keyword-matching
    blueprints have no AU provider, so 'first match' would falsely fail.
    """
    keywords = PRODUCT_TYPE_TO_BLUEPRINT_KEYWORDS.get(product_type, [])
    if not keywords:
        return []
    out: list[dict[str, Any]] = []
    for bp in blueprints:
        haystack = " ".join(
            str(bp.get(field, "")).lower() for field in ("title", "type", "brand", "model")
        )
        if any(k in haystack for k in keywords):
            out.append(bp)
    return out


def _is_au(provider: dict[str, Any]) -> bool:
    """True if this provider is one of the known AU print houses.

    Why id-based and not location-based: the /catalog/blueprints/{bp}/print_providers.json
    endpoint returns only {id, title, decoration_methods} — there's no location
    field at all. Checking provider["location"]["country"] always returns False
    there, even for The Print Bar / Prima Printing. The global providers list
    has location data, but cross-referencing 1409 blueprints against it on every
    run would be wasteful. The set of AU providers on Printify is tiny and
    stable, so a hard-coded id set is the right tradeoff.
    """
    return provider.get("id") in AU_PROVIDER_IDS


def _min_variant_price(variants: list[dict[str, Any]]) -> float:
    """Printify prices come as integer cents — return AUD float, or inf if empty."""
    available = [v for v in variants if v.get("is_available", True)]
    if not available:
        return float("inf")
    cheapest = min((v.get("price") or 0) for v in available)
    return cheapest / 100.0


async def _resolve_provider_for_idea(idea: ProductIdea) -> dict[str, Any]:
    """Run the catalogue lookup for a single idea and return a result dict.

    Iterates every blueprint whose title matches our keyword list, fetches its
    provider list, and considers only providers in AU_PROVIDER_IDS. Among all
    (blueprint, AU provider) pairs with available variants, returns the
    cheapest by base variant price. Stops scanning early once we've found a
    confirmed AU-producible blueprint with cost data — most product types only
    need to look at the first few matches.

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
    matches = _matching_blueprints(product_type, blueprints)
    if not matches:
        return {"ok": False, "reason": f"no blueprint match for product_type={product_type!r}"}

    best: dict[str, Any] | None = None
    scanned = 0
    for blueprint in matches:
        scanned += 1
        providers = await printify.get_print_providers(blueprint["id"])
        au_providers = [p for p in providers if _is_au(p)]
        if not au_providers:
            continue
        for provider in au_providers:
            variants_resp = await printify.get_variants(blueprint["id"], provider["id"])
            variants = variants_resp.get("variants") or []
            if not variants:
                continue
            base = _min_variant_price(variants)
            if base == float("inf"):
                continue
            # Catalog endpoint usually returns 0 (no price field exists on
            # catalog variants). Fall back to a per-product-type estimate so
            # listing_agent doesn't compute a retail of $1.95.
            if base <= 0:
                base = _DEFAULT_BASE_COST_AUD.get(product_type, 10.0)
            candidate = {
                "blueprint_id": blueprint["id"],
                "print_provider_id": provider["id"],
                "provider_name": provider.get("title") or provider.get("name") or "Unknown",
                "variant_ids": [v["id"] for v in variants if v.get("is_available", True)],
                "base_cost": base,
            }
            if best is None or candidate["base_cost"] < best["base_cost"]:
                best = candidate
        # Early-exit heuristic: once we've found at least one AU-producible
        # blueprint AND scanned a reasonable window of matches, stop. Otherwise
        # a "t-shirt" search would walk 253 blueprints every time.
        if best is not None and scanned >= 8:
            break

    if best is None:
        return {
            "ok": False,
            "reason": f"no AU print providers across {len(matches)} matching blueprints for {product_type!r}",
        }

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
