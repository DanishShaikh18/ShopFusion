# backend/app/services/scraper/amazon_scraper.py
from __future__ import annotations

from typing import Dict, List, Optional
import logging

# Reuse your existing scraper implementation
# Adjust import path if different
from ...services import scraper_india # if scraper_india is at backend/app/services/

logger = logging.getLogger(__name__)

def search_amazon(query: str, max_results: int = 6, api_key: Optional[str] = None, amazon_domain: str = "amazon.in") -> List[Dict]:
    """
    Thin adapter that calls your existing amazon scraper logic and returns normalized items.
    """
    logger.info("amazon_scraper.search_amazon query=%s", query)
    # If scraper_india.search already returns normalized items matching your unified schema,
    # just call it. Otherwise you can normalize further here.
    items = scraper_india.search(query=query, max_results=max_results, api_key=api_key, amazon_domain=amazon_domain)
    # ensure each item has "source" set to a short name
    for it in items:
        it.setdefault("source", "Amazon")
    return items
