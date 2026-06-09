"""Resilient one-shot: refresh the Etsy access token (retrying through the flaky
proxy) and PERSIST the rotated access+refresh tokens back into .env, so later
script runs use a valid token without re-refreshing every process start."""

import asyncio
import re
from pathlib import Path

import config
from api import etsy

ENV = Path(__file__).resolve().parent / ".env"


def _persist(access: str, refresh: str) -> None:
    text = ENV.read_text(encoding="utf-8")
    text = re.sub(r"^ETSY_ACCESS_TOKEN=.*$", f"ETSY_ACCESS_TOKEN={access}", text, flags=re.M)
    text = re.sub(r"^ETSY_REFRESH_TOKEN=.*$", f"ETSY_REFRESH_TOKEN={refresh}", text, flags=re.M)
    ENV.write_text(text, encoding="utf-8")


async def main() -> None:
    last = None
    for attempt in range(1, 7):
        try:
            tok = await etsy.refresh_access_token()
            acc, ref = tok.get("access_token"), tok.get("refresh_token")
            if acc and ref:
                _persist(acc, ref)
                print(f"[refresh] attempt {attempt} OK — persisted. "
                      f"access ...{acc[-6:]}  refresh ...{ref[-6:]}")
                return
            print(f"[refresh] attempt {attempt}: missing tokens in response: {tok}")
            return
        except Exception as e:
            last = str(e)[:160]
            print(f"[refresh] attempt {attempt} failed: {last}")
            await asyncio.sleep(5)
    print(f"[refresh] all attempts failed; last: {last}")


if __name__ == "__main__":
    asyncio.run(main())
