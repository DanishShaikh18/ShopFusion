"""
Minimal, clean FastAPI router for product search.

- Keeps only the endpoints required for immediate use:
  - POST /products/       -> calls scraper (real search)
  - POST /products/mock   -> returns static mock data (works without SERPAPI_KEY)
- Keeps a small /duplicates stub for future work.
- Removes extra noise, complex error details, and unnecessary imports.
- Uses asyncio.to_thread with a short timeout guard to call the blocking scraper.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import scraper_india as india_scraper

router = APIRouter(prefix="")  # main app includes this router under /products
logger = logging.getLogger("uvicorn.error")

# --- Schemas ---------------------------------------------------------------


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


# --- Config ----------------------------------------------------------------

# Timeout (seconds) for blocking scraper calls
SCRAPER_TIMEOUT = 30.0


# --- Endpoints -------------------------------------------------------------


@router.post("/", response_model=ProductSearchResponse)
async def search_products(payload: ProductSearchRequest):
    """
    Run a search via the blocking scraper in a thread and return typed results.
    Raises HTTP 504 on timeout, 500 on unexpected errors.
    """
    logger.info("product.search_products query=%s max_results=%d", payload.query, payload.max_results)

    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(india_scraper.search, payload.query, payload.max_results),
            timeout=SCRAPER_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.exception("Scraper timed out for query=%s", payload.query)
        raise HTTPException(status_code=504, detail="Scraper timed out; try a smaller max_results value.")
    except Exception as exc:  # pragma: no cover - surface unexpected scraper errors
        logger.exception("Scraper failed for query=%s: %s", payload.query, exc)
        raise HTTPException(status_code=500, detail="Search failed due to an internal error.")

    if not isinstance(results, list):
        logger.error("Scraper returned non-list result for query=%s: %r", payload.query, results)
        raise HTTPException(status_code=500, detail="Scraper returned unexpected result type.")

    # Convert and validate using Pydantic (keeps output schema stable)
    try:
        products = [ProductItem(**p) for p in results]
    except Exception as exc:
        logger.exception("Failed to convert scraper output to ProductItem: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to parse scraper results.")

    return ProductSearchResponse(query=payload.query, total_results=len(products), products=products)


# @router.post("/mock", response_model=ProductSearchResponse)
# async def mock_search(payload: ProductSearchRequest):
#     """
#     Simple mock endpoint useful when SERPAPI_KEY is not available.
#     """
#     logger.info("product.mock_search query=%s", payload.query)
#     mock_items = [
#         ProductItem(title="Mock Phone A", price_raw="₹12,999", price=12999.0, link="https://example.com/a", image=None, rating=4.3, source="Mock"),
#         ProductItem(title="Mock Phone B", price_raw="₹9,999", price=9999.0, link="https://example.com/b", image=None, rating=4.0, source="Mock"),
#     ]
#     # Respect requested max_results
#     items = mock_items[: payload.max_results] if payload.max_results and payload.max_results > 0 else mock_items
#     return ProductSearchResponse(query=payload.query, total_results=len(items), products=items)


# @router.post("/duplicates")
# async def search_duplicates(payload: ProductSearchRequest):
#     """
#     Minimal stub: returns scraped products and a placeholder duplicates field.
#     Keep this small until duplication logic is implemented.
#     """
#     try:
#         results = await asyncio.wait_for(
#             asyncio.to_thread(india_scraper.search, payload.query, payload.max_results),
#             timeout=SCRAPER_TIMEOUT,
#         )
#     except asyncio.TimeoutError:
#         raise HTTPException(status_code=504, detail="Scraper timed out")
#     except Exception:
#         raise HTTPException(status_code=500, detail="Duplicate scan failed")

#     return {"query": payload.query, "products": results, "duplicates": []}
