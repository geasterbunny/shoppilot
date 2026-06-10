"""Prove the dark-fabric designs are correct: fetch the actual uploaded
transparent PNGs from Printify and composite them onto black/cream fabric."""

import asyncio
import io
import ssl

import httpx
import truststore
from PIL import Image

import config
from database import Listing, SessionLocal, SupplierProduct

ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
HEADERS = {"Authorization": f"Bearer {config.PRINTIFY_API_KEY}", "User-Agent": "ShopPilot/1.0"}


async def _upload_preview(image_id: str) -> str:
    async with httpx.AsyncClient(timeout=60, verify=ctx) as c:
        r = await c.get(f"https://api.printify.com/v1/uploads/{image_id}.json", headers=HEADERS)
    r.raise_for_status()
    return r.json().get("preview_url")


async def _bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60, verify=ctx) as c:
        return (await c.get(url)).content


def mock(design_bytes: bytes, dst: str, colour):
    shirt = Image.new("RGBA", (1000, 1180), colour + (255,))
    d = Image.open(io.BytesIO(design_bytes)).convert("RGBA")
    tw = int(shirt.width * 0.52); th = int(d.height * tw / d.width)
    d = d.resize((tw, th))
    shirt.alpha_composite(d, ((shirt.width - tw) // 2, int(shirt.height * 0.20)))
    shirt.convert("RGB").save(dst)


async def main():
    db = SessionLocal()
    targets = {12: ((28, 28, 30), "_dark_result_tee12.png"),
               7: ((232, 224, 200), "_dark_result_tote7.png")}  # tote dark variant is on black; show on black too
    targets[7] = ((28, 28, 30), "_dark_result_tote7.png")
    for iid, (colour, dst) in targets.items():
        sup = db.query(SupplierProduct).filter(SupplierProduct.idea_id == iid).first()
        if not sup.image_id_dark:
            print(f"idea {iid}: no dark design"); continue
        url = await _upload_preview(sup.image_id_dark)
        mock(await _bytes(url), dst, colour)
        print(f"idea {iid}: dark design {sup.image_id_dark} -> {dst}")
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
