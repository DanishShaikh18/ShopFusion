"""
Minimal, clean FastAPI router for product search.

- POST /products/       -> calls unified multi-source manager (Amazon + Google Shopping)
- POST /products/mock   -> static mock results (no API key required)
- POST /products/duplicates -> stub for future
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# NEW: use the aggregator manager instead of scraper_india
from app.services.scraper.manager import search_all

router = APIRouter(prefix="")
logger = logging.getLogger("uvicorn.error")

# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------

class ProductSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: int = Field(6, ge=1, le=50)


class ProductItem(BaseModel):
    title: str
    price_raw: Optional[str] = None
    price: Optional[float] = None
    link: Optional[str] = None
    image: Optional[str] = None
    rating: Optional[float] = None
    source: str


class ProductSearchResponse(BaseModel):
    query: str
    total_results: int
    products: List[ProductItem]


SCRAPER_TIMEOUT = 30.0


# --------------------------------------------------------------------------
# MAIN PRODUCT SEARCH (Amazon + Google Shopping)
# --------------------------------------------------------------------------

@router.post("/", response_model=ProductSearchResponse)
async def search_products(payload: ProductSearchRequest):
    """
    Unified search that calls ALL scrapers via manager.py.
    Runs in a separate thread (blocking-safe) and respects a timeout.
    """
    logger.info("product.search_products query=%s max_results=%d", payload.query, payload.max_results)

    try:
        # RUN MULTI-SOURCE SCRAPER
        results = await asyncio.wait_for(
            asyncio.to_thread(search_all, payload.query, payload.max_results),
            timeout=SCRAPER_TIMEOUT,
        )

    except asyncio.TimeoutError:
        logger.exception("Scraper timed out for query=%s", payload.query)
        raise HTTPException(status_code=504, detail="Scraper timed out; try a smaller max_results value.")

    except Exception as exc:
        logger.exception("Unified scraper failed: %s", exc)
        raise HTTPException(status_code=500, detail="Search failed due to an internal error.")

    if not isinstance(results, list):
        logger.error("Scraper returned non-list result for query=%s: %r", payload.query, results)
        raise HTTPException(status_code=500, detail="Unexpected scraper output format.")

    # Convert to validated Pydantic models
    try:
        products = [ProductItem(**p) for p in results]
    except Exception as exc:
        logger.exception("Failed to convert scraper output: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to parse scraper results.")

    return ProductSearchResponse(
        query=payload.query,
        total_results=len(products),
        products=products
    )


# --------------------------------------------------------------------------
# MOCK ENDPOINT
# --------------------------------------------------------------------------

@router.post("/mock", response_model=ProductSearchResponse)
async def mock_search(payload: ProductSearchRequest):
    mock_items = [
        ProductItem(title="Mock Phone A", price_raw="₹12,999", price=12999.0, link="https://example.com/a", image=None, rating=4.3, source="Mock"),
        ProductItem(title="Mock Phone B", price_raw="₹9,999", price=9999.0, link="https://example.com/b", image=None, rating=4.0, source="Mock"),
    ]
    items = mock_items[: payload.max_results]
    return ProductSearchResponse(query=payload.query, total_results=len(items), products=items)


# --------------------------------------------------------------------------
# DUPLICATE SCAN (placeholder)
# --------------------------------------------------------------------------

@router.post("/duplicates")
async def search_duplicates(payload: ProductSearchRequest):
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(search_all, payload.query, payload.max_results),
            timeout=SCRAPER_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Scraper timed out")
    except Exception:
        raise HTTPException(status_code=500, detail="Duplicate scan failed")

    return {"query": payload.query, "products": results, "duplicates": []}
