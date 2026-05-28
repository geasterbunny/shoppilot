"""Dry-run: print the Ideogram prompts that would be generated for each idea."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config
config.MOCK_DESIGN = True  # don't call any API

from database import SessionLocal, ProductIdea, SupplierProduct
from agents.design_agent import _build_prompt

db = SessionLocal()
pending = (
    db.query(SupplierProduct, ProductIdea)
    .join(ProductIdea, SupplierProduct.idea_id == ProductIdea.id)
    .all()
)
for supplier, idea in pending:
    prompt, aspect = _build_prompt(idea)
    print(f"=== idea {idea.id} ({idea.product_type}) [{aspect}] ===")
    print(prompt)
    print()
db.close()
