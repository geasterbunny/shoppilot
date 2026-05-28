"""Print full preview URLs for the 4 Ideogram designs in Printify."""
import asyncio, ssl, httpx, truststore, config, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_SSL = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
HEADERS = {"Authorization": f"Bearer {config.PRINTIFY_API_KEY}", "User-Agent": "ShopPilot/1.0"}
IDS = [
    "6a1419f14d5df0b0477b800f",
    "6a1419f731359e5c876e5116",
    "6a1419fa53accc0d0794dc87",
    "6a1419ffecb18e5fc5d7a51c",
]

async def main():
    async with httpx.AsyncClient(timeout=30, verify=_SSL) as c:
        for img_id in IDS:
            r = await c.get(f"https://api.printify.com/v1/uploads/{img_id}.json", headers=HEADERS)
            img = r.json()
            print(img_id, img.get("file_name"))
            print(" ", img.get("preview_url"))
            print()

asyncio.run(main())
