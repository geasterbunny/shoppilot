from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

import scheduler as scheduler_module
from agents import (
    design_agent,
    idea_agent,
    listing_agent,
    marketing_agent,
    research_agent,
    supplier_agent,
)
from api import etsy
from database import (
    Listing,
    MarketingPost,
    ProductIdea,
    ResearchProduct,
    SupplierProduct,
    get_session,
    init_db,
)

DASHBOARD_FILE = Path(__file__).resolve().parent / "dashboard" / "index.html"

_pending_code_verifier: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler_module.start()
    try:
        yield
    finally:
        scheduler_module.shutdown()


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
    # NB: do not clear the verifier yet — if the token exchange fails (network,
    # SSL, Etsy 4xx), we want the user to be able to retry hitting Etsy with the
    # SAME code_challenge rather than restarting /auth/etsy. Only clear on success.

    tokens = await etsy.exchange_code_for_tokens(code, verifier)
    _pending_code_verifier = None

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


@app.get("/shops/mine")
async def get_my_shops():
    return await etsy.get_my_shops()


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


@app.post("/agents/supplier/run")
async def run_supplier_agent(db: Session = Depends(get_session)):
    return await supplier_agent.run(db)


@app.get("/suppliers")
def list_suppliers(db: Session = Depends(get_session)):
    """Return supplier matches joined with idea title for the dashboard."""
    rows = (
        db.query(SupplierProduct, ProductIdea.product_title)
        .outerjoin(ProductIdea, SupplierProduct.idea_id == ProductIdea.id)
        .order_by(SupplierProduct.created_at.desc())
        .all()
    )
    return [
        {
            "id": supplier.id,
            "idea_id": supplier.idea_id,
            "idea_title": idea_title,
            "blueprint_id": supplier.blueprint_id,
            "print_provider_id": supplier.print_provider_id,
            "provider_name": supplier.provider_name,
            "variant_ids": supplier.variant_ids,
            "base_cost": supplier.base_cost,
            "created_at": supplier.created_at.isoformat() if supplier.created_at else None,
        }
        for supplier, idea_title in rows
    ]


@app.post("/run/design")
async def run_design_agent(db: Session = Depends(get_session)):
    return await design_agent.run(db)


@app.post("/agents/listing/run")
async def run_listing_agent(db: Session = Depends(get_session)):
    return await listing_agent.run(db)


@app.get("/listings")
def list_listings(db: Session = Depends(get_session)):
    """Return all listings joined with the underlying idea title for the dashboard."""
    rows = (
        db.query(Listing, ProductIdea.product_title)
        .outerjoin(ProductIdea, Listing.idea_id == ProductIdea.id)
        .order_by(Listing.created_at.desc())
        .all()
    )
    return [
        {
            "id": listing.id,
            "idea_id": listing.idea_id,
            "idea_title": idea_title,
            "printify_product_id": listing.printify_product_id,
            "etsy_listing_id": listing.etsy_listing_id,
            "status": listing.status,
            "published_at": listing.published_at.isoformat() if listing.published_at else None,
            "created_at": listing.created_at.isoformat() if listing.created_at else None,
        }
        for listing, idea_title in rows
    ]


@app.post("/agents/marketing/run")
async def run_marketing_agent(db: Session = Depends(get_session)):
    return await marketing_agent.run(db)


@app.get("/marketing")
def list_marketing_posts(db: Session = Depends(get_session)):
    """Return marketing posts joined with the underlying idea title."""
    rows = (
        db.query(MarketingPost, ProductIdea.product_title)
        .outerjoin(Listing, MarketingPost.listing_id == Listing.id)
        .outerjoin(ProductIdea, Listing.idea_id == ProductIdea.id)
        .order_by(MarketingPost.scheduled_at.asc())
        .all()
    )
    return [
        {
            "id": post.id,
            "listing_id": post.listing_id,
            "idea_title": idea_title,
            "platform": post.platform,
            "post_content": post.post_content,
            "postiz_post_id": post.postiz_post_id,
            "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
            "created_at": post.created_at.isoformat() if post.created_at else None,
        }
        for post, idea_title in rows
    ]


@app.get("/scheduler/jobs")
def list_scheduled_jobs():
    """Snapshot of currently-scheduled jobs (research + chained idea_job)."""
    return scheduler_module.list_jobs()


@app.post("/scheduler/research/trigger")
async def trigger_research_now():
    """Kick the research job out-of-cycle. Idea job is auto-queued ~1h after."""
    return await scheduler_module.trigger_research_now()


@app.get("/dashboard")
def dashboard():
    if not DASHBOARD_FILE.exists():
        raise HTTPException(status_code=500, detail=f"Dashboard file missing at {DASHBOARD_FILE}")
    return FileResponse(DASHBOARD_FILE, media_type="text/html")
