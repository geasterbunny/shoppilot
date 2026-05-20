"""One-off diagnostic for /shops/mine 500.

Run with: .\.venv\Scripts\python.exe _diagnose_etsy.py

This script is intentionally self-contained and does NOT echo secrets. It
prints lengths, whitespace flags, and the actual exception we'd hit through
the FastAPI route, so we can tell whether the failure is:
  - missing/blank shared secret
  - access token expired (401)
  - shared-secret rejected (403)
  - network/SSL
  - something else
"""

from __future__ import annotations

import asyncio
import traceback

import config
from api import etsy


def has_ws(s: str) -> bool:
    return s != s.strip() if s else False


def show(name: str, val: str) -> None:
    if not val:
        print(f"  {name:24} = (empty)")
        return
    print(f"  {name:24} = len={len(val):3}  whitespace={has_ws(val)}")


async def main() -> None:
    print("=== config snapshot ===")
    show("ETSY_API_KEY",        config.ETSY_API_KEY)
    show("ETSY_SHARED_SECRET",  config.ETSY_SHARED_SECRET)
    show("ETSY_ACCESS_TOKEN",   config.ETSY_ACCESS_TOKEN)
    show("ETSY_REFRESH_TOKEN",  config.ETSY_REFRESH_TOKEN)
    show("ETSY_SHOP_ID",        config.ETSY_SHOP_ID)
    print(f"  MOCK_ETSY                = {config.MOCK_ETSY}")

    if config.ETSY_ACCESS_TOKEN:
        user_id_part = config.ETSY_ACCESS_TOKEN.split(".", 1)[0]
        print(f"  derived user_id          = {user_id_part!r}  (looks_numeric={user_id_part.isdigit()})")

    print()
    print("=== try /shops/mine as the FastAPI route does ===")
    failure: Exception | None = None
    try:
        result = await etsy.get_my_shops()
        print("  SUCCESS — first 400 chars of response:")
        print(f"  {str(result)[:400]}")
        return
    except etsy.EtsyAPIError as e:
        print(f"  EtsyAPIError: status={e.status_code}")
        print(f"  body (first 500 chars): {e.body[:500] if e.body else '(empty)'}")
        failure = e
    except Exception as e:
        print(f"  Exception: {type(e).__name__}: {e}")
        traceback.print_exc()
        failure = e

    # Etsy v3 rotates refresh tokens on every use — calling refresh_access_token()
    # invalidates whatever is currently in .env. Only refresh when the failure
    # is clearly an auth/expiry issue (401), NOT for 403 (which means the
    # shared secret is missing/wrong, and the token is fine).
    if not isinstance(failure, etsy.EtsyAPIError) or failure.status_code != 401:
        print()
        print("=== refresh skipped ===")
        print("  Not refreshing because the failure isn't a 401 (expired token).")
        print("  Fix the root cause above, then re-run.")
        return

    print()
    print("=== attempt refresh_access_token() (status was 401) ===")
    if not config.ETSY_REFRESH_TOKEN:
        print("  skipping — ETSY_REFRESH_TOKEN is empty")
        return
    try:
        tokens = await etsy.refresh_access_token()
    except etsy.EtsyAPIError as e:
        print(f"  EtsyAPIError on refresh: status={e.status_code}")
        print(f"  body: {e.body[:500] if e.body else '(empty)'}")
        return
    except Exception as e:
        print(f"  Refresh exception: {type(e).__name__}: {e}")
        traceback.print_exc()
        return

    new_access = tokens.get("access_token", "")
    new_refresh = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in")
    print(f"  REFRESH OK — expires_in={expires_in}s")
    print(f"  new ETSY_ACCESS_TOKEN  (first 8 / last 4): {new_access[:8]}...{new_access[-4:]}  (len={len(new_access)})")
    print(f"  new ETSY_REFRESH_TOKEN (first 8 / last 4): {new_refresh[:8]}...{new_refresh[-4:]}  (len={len(new_refresh)})")
    print()
    print("  >>> PASTE THESE INTO .env, RESTART start.bat, AND RE-TRY /shops/mine <<<")
    print()
    print("  Full values follow on next two lines — copy from terminal:")
    print(f"  ETSY_ACCESS_TOKEN={new_access}")
    print(f"  ETSY_REFRESH_TOKEN={new_refresh}")


if __name__ == "__main__":
    asyncio.run(main())
