"""Hit Printify's global providers list and see which are AU.

The blueprint-scoped endpoint returns a lightweight shape with no location.
The global endpoint returns the full provider record including location.
"""

from __future__ import annotations

import asyncio
import json

from api.printify import _request


async def main() -> None:
    providers = await _request("GET", "/catalog/print_providers.json")
    print(f"total providers globally: {len(providers)}")
    print()
    au = []
    for p in providers:
        loc = p.get("location") or {}
        country = (loc.get("country") or loc.get("country_code") or "").upper()
        if country in ("AU", "AUS"):
            au.append(p)
    print(f"AU providers: {len(au)}")
    for p in au:
        print("  " + json.dumps(p, default=str))
    print()
    print("Sample of first 5 providers (any country):")
    for p in providers[:5]:
        print("  " + json.dumps(p, default=str))
    print()
    # Tally by country
    by_country: dict[str, int] = {}
    for p in providers:
        loc = p.get("location") or {}
        c = (loc.get("country") or loc.get("country_code") or "??").upper()
        by_country[c] = by_country.get(c, 0) + 1
    print("Providers by country:")
    for c, n in sorted(by_country.items(), key=lambda kv: -kv[1]):
        print(f"  {c}: {n}")


if __name__ == "__main__":
    asyncio.run(main())
