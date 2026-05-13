from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse

from api import etsy
from database import init_db

_pending_code_verifier: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ShopPilot", lifespan=lifespan)


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.get("/auth/etsy")
def auth_etsy():
    global _pending_code_verifier
    url, verifier = etsy.generate_auth_url()
    _pending_code_verifier = verifier
    return RedirectResponse(url)


@app.get("/auth/etsy/callback")
async def auth_etsy_callback(
    code: str = Query(...),
    state: str | None = Query(None),
    error: str | None = Query(None),
):
    global _pending_code_verifier

    if error:
        raise HTTPException(status_code=400, detail=f"Etsy returned error: {error}")
    if not _pending_code_verifier:
        raise HTTPException(
            status_code=400,
            detail="No pending OAuth flow. Start over at /auth/etsy.",
        )

    verifier = _pending_code_verifier
    _pending_code_verifier = None

    tokens = await etsy.exchange_code_for_tokens(code, verifier)

    print("=========== Etsy OAuth tokens ===========")
    print(f"access_token:  {tokens.get('access_token')}")
    print(f"refresh_token: {tokens.get('refresh_token')}")
    print(f"expires_in:    {tokens.get('expires_in')}")
    print(f"token_type:    {tokens.get('token_type')}")
    print("=========================================")
    print("Copy these into .env as ETSY_ACCESS_TOKEN and ETSY_REFRESH_TOKEN.")

    return {
        "status": "ok",
        "message": "Tokens printed to console. Copy them into .env as ETSY_ACCESS_TOKEN and ETSY_REFRESH_TOKEN.",
    }
