"""For each AU provider, list which blueprints they print and at what cost.

Printify has GET /v1/catalog/print_providers/{id}.json which returns
the provider record. There's also /v1/catalog/print_providers/{id}/blueprints.json
in some account tiers — try both and dump.
"""

from __future__ import annotations

import asyncio

from api.printify import _request

AU_PROVIDER_IDS = [34, 66]  # The Print Bar; Prima Printing


async def main() -> None:
    # Cross-reference: walk every blueprint, fetch its provider list, see if
    # any AU id appears. Cheaper than 1409 individual lookups would be the
    # per-provider blueprints endpoint, but that's not always exposed —
    # falling back to the brute force which we know works.
    blueprints = await _request("GET", "/catalog/blueprints.json")
    print(f"scanning {len(blueprints)} blueprints for AU provider availability...")

    hits: list[dict] = []  # rows: (bp_id, bp_title, bp_type, au_provider_id)
    scanned = 0
    for bp in blueprints:
        scanned += 1
        try:
            providers = await _request(
                "GET", f"/catalog/blueprints/{bp['id']}/print_providers.json"
            )
        except Exception:
            continue
        au_for_this = [p for p in providers if p.get("id") in AU_PROVIDER_IDS]
        if au_for_this:
            for p in au_for_this:
                hits.append({
                    "bp_id": bp["id"],
                    "bp_title": bp.get("title"),
                    "bp_type": bp.get("type") or bp.get("brand"),
                    "provider_id": p["id"],
                    "provider_title": p.get("title"),
                })
        if scanned % 100 == 0:
            print(f"  ...scanned {scanned}/{len(blueprints)}, AU hits so far: {len(hits)}")

    print(f"\ntotal AU-printable blueprints: {len(hits)}")
    print()
    # Group output by provider then by likely product category keyword
    by_provider: dict[int, list[dict]] = {}
    for h in hits:
        by_provider.setdefault(h["provider_id"], []).append(h)
    for pid, rows in by_provider.items():
        title = rows[0]["provider_title"]
        print(f"=== provider {pid} ({title}) — {len(rows)} blueprint(s) ===")
        for r in rows:
            print(f"  bp {r['bp_id']:>5}  {r['bp_title']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
