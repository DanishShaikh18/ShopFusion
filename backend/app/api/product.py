# backend/app/api/product.py

"""
FastAPI router for product search.

Endpoints:
- POST /products/       -> unified smart product search
- POST /products/mock   -> static mock results (no API key required)
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
    is_recommended: Optional[bool] = False



class ProductSearchResponse(BaseModel):
    query: str
    total_results: int
    products: List[ProductItem]


SCRAPER_TIMEOUT = 30.0

# --------------------------------------------------------------------------
# MAIN PRODUCT SEARCH
# --------------------------------------------------------------------------

@router.post("/", response_model=ProductSearchResponse)
async def search_products(payload: ProductSearchRequest):
    """
    Smart product search:
    - Calls unified manager
    - Filters irrelevant results
    - Returns clean, ranked products
    """
    logger.info(
        "product.search_products query=%s max_results=%d",
        payload.query,
        payload.max_results,
    )

    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(
                search_all,
                payload.query,
                payload.max_results,
            ),
            timeout=SCRAPER_TIMEOUT,
        )

    except asyncio.TimeoutError:
        logger.exception("Search timed out for query=%s", payload.query)
        raise HTTPException(
            status_code=504,
            detail="Search timed out. Try reducing max results.",
        )

    except Exception as exc:
        logger.exception("Search failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Search failed due to an internal error.",
        )

    if not isinstance(results, list):
        logger.error("Unexpected result format: %r", results)
        raise HTTPException(
            status_code=500,
            detail="Unexpected search output format.",
        )

    try:
        products = [ProductItem(**item) for item in results]
    except Exception as exc:
        logger.exception("Response validation failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to parse search results.",
        )

    return ProductSearchResponse(
        query=payload.query,
        total_results=len(products),
        products=products,
    )

# --------------------------------------------------------------------------
# MOCK ENDPOINT (DEV / DEMO)
# --------------------------------------------------------------------------

@router.post("/mock", response_model=ProductSearchResponse)
async def mock_search(payload: ProductSearchRequest):
    mock_items = [
        ProductItem(
            title="Mock Phone A",
            price_raw="₹12,999",
            price=12999.0,
            link="https://example.com/a",
            image=None,
            rating=4.3,
            source="Mock",
        ),
        ProductItem(
            title="Mock Phone B",
            price_raw="₹9,999",
            price=9999.0,
            link="https://example.com/b",
            image=None,
            rating=4.0,
            source="Mock",
        ),
    ]

    items = mock_items[: payload.max_results]

    return ProductSearchResponse(
        query=payload.query,
        total_results=len(items),
        products=items,
    )
