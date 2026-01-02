# backend/app/services/scraper/google_shopping_scraper.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
import time
import logging

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())


from serpapi import GoogleSearch  # ensure google-search-results installed

logger = logging.getLogger(__name__)

RETRIES = 2
RETRY_SLEEP = 1.0

def _fetch_google_shopping(api_key: str, query: str, gl: str = "in", hl: str = "en", location: Optional[str] = None) -> Dict[str, Any]:
    params = {
        "engine": "google_shopping",
        "q": query,
        "api_key": api_key,
        "gl": gl,
        "hl": hl,
    }
    if location:
        params["location_requested"] = location
        params["location_used"] = location

    last_exc = None
    for attempt in range(1, RETRIES + 1):
        try:
            search = GoogleSearch(params)
            data = search.get_dict()
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            last_exc = exc
            logger.warning("google_shopping attempt %d failed: %s", attempt, exc)
            time.sleep(RETRY_SLEEP * attempt)
    raise RuntimeError("google_shopping request failed") from last_exc

def _normalize_shopping_item(item: Dict[str, Any]) -> Dict[str, Any]:
    title = item.get("title")
    link = item.get("product_link") or item.get("serpapi_immersive_product_api") or item.get("link")
    price_raw = item.get("price") or item.get("displayed_price")
    price = item.get("extracted_price") or None
    image = item.get("thumbnail") or item.get("serpapi_thumbnail")
    rating = item.get("rating")
    source = item.get("source") or item.get("merchant") or "GoogleShopping"
    delivery = item.get("delivery")
    condition = item.get("second_hand_condition") or item.get("condition") or None

    return {
        "title": title,
        "price_raw": price_raw,
        "price": float(price) if price is not None else None,
        "link": link,
        "image": image,
        "rating": float(rating) if rating is not None else None,
        "source": source,
        "delivery": delivery,
        "condition": condition,
        "_raw": item,
    }

def search_google_shopping(api_key: str, query: str, max_results: int = 10, gl: str = "in", hl: str = "en", location: Optional[str] = None) -> List[Dict[str, Any]]:
    raw = _fetch_google_shopping(api_key=api_key, query=query, gl=gl, hl=hl, location=location)
    results = raw.get("shopping_results") or []
    normalized = []
    for item in results:
        try:
            normalized.append(_normalize_shopping_item(item))
            if len(normalized) >= max_results:
                break
        except Exception:
            continue
    return normalized
