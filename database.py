from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

from config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ResearchProduct(Base):
    __tablename__ = "research_products"

    id = Column(Integer, primary_key=True)
    etsy_listing_id = Column(Text)
    title = Column(Text)
    price = Column(Float)
    favourites = Column(Integer)
    views = Column(Integer)
    score = Column(Float)
    tags = Column(Text)
    shop_name = Column(Text)
    discovered_at = Column(DateTime, server_default=func.current_timestamp())


class ProductIdea(Base):
    __tablename__ = "product_ideas"

    id = Column(Integer, primary_key=True)
    product_title = Column(Text)
    product_type = Column(Text)
    description = Column(Text)
    tags = Column(Text)
    target_buyer = Column(Text)
    printify_search_term = Column(Text)
    status = Column(Text, default="pending_review")
    created_at = Column(DateTime, server_default=func.current_timestamp())


class SupplierProduct(Base):
    __tablename__ = "supplier_products"

    id = Column(Integer, primary_key=True)
    idea_id = Column(Integer, ForeignKey("product_ideas.id"))
    blueprint_id = Column(Integer)
    print_provider_id = Column(Integer)
    provider_name = Column(Text)
    variant_ids = Column(Text)
    base_cost = Column(Float)
    created_at = Column(DateTime, server_default=func.current_timestamp())


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True)
    idea_id = Column(Integer, ForeignKey("product_ideas.id"))
    printify_product_id = Column(Text)
    etsy_listing_id = Column(Text)
    status = Column(Text, default="draft")
    published_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.current_timestamp())


class MarketingPost(Base):
    __tablename__ = "marketing_posts"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"))
    platform = Column(Text)
    post_content = Column(Text)
    postiz_post_id = Column(Text)
    scheduled_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.current_timestamp())


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
