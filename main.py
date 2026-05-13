from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from agents import idea_agent, research_agent
from api import etsy
from database import ProductIdea, ResearchProduct, get_session, init_db

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


@app.post("/agents/research/run")
async def run_research_agent(db: Session = Depends(get_session)):
    return await research_agent.run(db)


@app.get("/research")
def list_research_products(db: Session = Depends(get_session)):
    rows = (
        db.query(ResearchProduct)
        .order_by(ResearchProduct.score.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "etsy_listing_id": r.etsy_listing_id,
            "title": r.title,
            "price": r.price,
            "favourites": r.favourites,
            "views": r.views,
            "score": r.score,
            "tags": r.tags,
            "shop_name": r.shop_name,
            "discovered_at": r.discovered_at.isoformat() if r.discovered_at else None,
        }
        for r in rows
    ]


@app.post("/agents/idea/run")
async def run_idea_agent(db: Session = Depends(get_session)):
    return await idea_agent.run(db)


@app.get("/ideas")
def list_ideas(db: Session = Depends(get_session)):
    rows = (
        db.query(ProductIdea)
        .order_by(ProductIdea.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "product_title": r.product_title,
            "product_type": r.product_type,
            "description": r.description,
            "tags": r.tags,
            "target_buyer": r.target_buyer,
            "printify_search_term": r.printify_search_term,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@app.post("/ideas/{idea_id}/approve")
def approve_idea(idea_id: int, db: Session = Depends(get_session)):
    idea = db.query(ProductIdea).filter(ProductIdea.id == idea_id).first()
    if idea is None:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")
    idea.status = "approved"
    db.commit()
    return {"id": idea.id, "status": idea.status}


@app.post("/ideas/{idea_id}/reject")
def reject_idea(idea_id: int, db: Session = Depends(get_session)):
    idea = db.query(ProductIdea).filter(ProductIdea.id == idea_id).first()
    if idea is None:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")
    idea.status = "rejected"
    db.commit()
    return {"id": idea.id, "status": idea.status}
