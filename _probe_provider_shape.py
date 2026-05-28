"""Dump the raw provider JSON for a few blueprints so we can see every field."""

from __future__ import annotations

import asyncio
import json

from api import printify


async def main() -> None:
    # Pick a few representative blueprints (a mug, a tee, a poster)
    sample_bp_ids = [68, 5, 282, 97]
    for bp_id in sample_bp_ids:
        print(f"\n=== blueprint {bp_id} ===")
        try:
            providers = await printify.get_print_providers(bp_id)
        except Exception as e:
            print(f"  failed: {e}")
            continue
        print(f"  {len(providers)} provider(s) total")
        # Show first 3 in full, plus any whose data contains 'AU' or 'AUS'
        seen_au_hint = False
        for i, p in enumerate(providers):
            raw = json.dumps(p, default=str)
            if "AU" in raw.upper() or "AUSTRALI" in raw.upper():
                print(f"  ** provider {i} has AU hint:")
                print("    " + raw)
                seen_au_hint = True
        if not seen_au_hint:
            print("  no provider mentions AU/Australia anywhere — sample of first 3:")
            for p in providers[:3]:
                print("    " + json.dumps(p, default=str))


if __name__ == "__main__":
    asyncio.run(main())
