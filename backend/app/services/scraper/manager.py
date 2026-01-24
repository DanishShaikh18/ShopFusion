# backend/app/services/scraper/manager.py
from __future__ import annotations

import os
import time
import math
import logging
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv, find_dotenv
from .google_shopping_scraper import search_google_shopping

load_dotenv(find_dotenv())
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Simple in-memory cache (DEV friendly)
# ------------------------------------------------------------------

_CACHE: Dict[str, Tuple[float, List[Dict]]] = {}
CACHE_TTL_SECONDS = 60


def _cache_get(key: str) -> Optional[List[Dict]]:
    entry = _CACHE.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: List[Dict]) -> None:
    _CACHE[key] = (time.time(), value)


# ------------------------------------------------------------------
# Source trust
# ------------------------------------------------------------------

SOURCE_TRUST = {
    "amazon": 1.00,
    "flipkart": 0.98,
    "myntra": 0.94,
    "nykaa": 0.93,
    "tira": 0.92,
    "sephora": 0.92,
    "tatacliq": 0.90,
    "tatacliq_luxury": 0.88,
    "croma": 0.90,
    "reliance": 0.90,
    "cashify": 0.70,
    "easyphones": 0.60,
    "meesho": 0.86,
    "alibaba": 0.30,
    "ali_express": 0.40,
}


def _get_trust_score(source: str) -> float:
    if not source:
        return 0.5
    s = source.lower()
    for key, score in SOURCE_TRUST.items():
        if key in s:
            return score
    return 0.5


# ------------------------------------------------------------------
# Merchant search redirect support
# ------------------------------------------------------------------

MERCHANT_SEARCH_URLS = {
    "amazon": "https://www.amazon.in/s?k={query}",
    "flipkart": "https://www.flipkart.com/search?q={query}",
    "myntra": "https://www.myntra.com/{query}",
    "nykaa": "https://www.nykaa.com/search/result/?q={query}",
    "tira": "https://www.tirabeauty.com/search?q={query}",
    "sephora": "https://www.sephora.in/search?q={query}",
    "tatacliq": "https://www.tatacliq.com/search/?searchCategory=all&text={query}",
    "croma": "https://www.croma.com/search/?text={query}",
    "reliance": "https://www.reliancedigital.in/search?q={query}",
}


def _is_google_redirect(url: str) -> bool:
    return "google.com/search" in url or "google.com/shopping" in url


def _build_merchant_search_link(source: str, query: str) -> Optional[str]:
    if not source:
        return None
    s = source.lower()
    for key, template in MERCHANT_SEARCH_URLS.items():
        if key in s:
            return template.format(query=query.replace(" ", "+"))
    return None


# ------------------------------------------------------------------
# Filters & scoring
# ------------------------------------------------------------------

IGNORE_KEYWORDS = {
    "cover", "case", "charger", "adapter", "cable", "protector",
    "screen guard", "tempered", "back cover", "earphone", "headphone"
}


def _is_irrelevant(title: str) -> bool:
    title = title.lower()
    return any(word in title for word in IGNORE_KEYWORDS)


def _score_item(item: Dict, query: str) -> float:
    score = 0.0
    title = (item.get("title") or "").lower()
    q_tokens = query.lower().split()

    for tok in q_tokens:
        if tok in title:
            score += 0.25

    if item.get("rating"):
        score += 0.20

    if item.get("price") is not None:
        score += 0.15

    return min(score, 1.0)


def _filter_price_outliers(items: List[Dict]) -> List[Dict]:
    prices = [i["price"] for i in items if isinstance(i.get("price"), (int, float))]
    if len(prices) < 3:
        return items

    prices.sort()
    mid = len(prices) // 2
    median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2

    low = median * 0.4
    high = median * 2.5

    return [
        i for i in items
        if i.get("price") is None or (low <= i["price"] <= high)
    ]


def _normalize_title_key(title: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else " " for ch in title).strip()


def _dedupe(items: List[Dict]) -> List[Dict]:
    seen = {}
    for item in items:
        key = item.get("link") or _normalize_title_key(item.get("title") or "")
        if not key:
            continue

        if key not in seen:
            seen[key] = item
        else:
            old = seen[key]
            if (
                item.get("price") is not None
                and old.get("price") is not None
                and item["price"] < old["price"]
            ):
                seen[key] = item
            elif (item.get("rating") or 0) > (old.get("rating") or 0):
                seen[key] = item

    return list(seen.values())


def _recommend_best(items: List[Dict]) -> None:
    best_item = None
    best_score = -1.0

    for item in items:
        relevance = item.get("_score") or 0
        rating = (item.get("rating") or 0) / 5
        trust = _get_trust_score(item.get("source"))

        final_score = (
            relevance * 0.45 +
            rating * 0.25 +
            trust * 0.30
        )

        if final_score > best_score:
            best_score = final_score
            best_item = item

    for item in items:
        item["is_recommended"] = (item is best_item)


# ------------------------------------------------------------------
# PUBLIC ENTRYPOINT
# ------------------------------------------------------------------

def search_all(
    query: str,
    max_results: int = 6,
    api_key: Optional[str] = None,
) -> List[Dict]:

    cache_key = f"{query}::{max_results}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    api_key = api_key or os.getenv("SERPAPI_KEY")

    try:
        raw_items = search_google_shopping(
            api_key=api_key,
            query=query,
            max_results=max_results * 3,
        )
    except Exception as exc:
        logger.warning("google shopping failed: %s", exc)
        return []

    cleaned: List[Dict] = []
    for item in raw_items:
        title = item.get("title")
        if not title or _is_irrelevant(title):
            continue

        item["_score"] = _score_item(item, query)
        cleaned.append(item)

    cleaned = _filter_price_outliers(cleaned)

    cleaned.sort(
        key=lambda x: (
            -(x.get("_score") or 0.0),
            x.get("price") or math.inf,
            -(x.get("rating") or 0.0),
        )
    )

    cleaned = _dedupe(cleaned)
    cleaned = cleaned[:max_results]

    _recommend_best(cleaned)

    # 🔗 Smart link handling
    for item in cleaned:
        link = item.get("link")
        if link and _is_google_redirect(link):
            merchant_link = _build_merchant_search_link(item.get("source"), query)
            if merchant_link:
                item["link"] = merchant_link
                item["link_type"] = "merchant_search"
            else:
                item["link_type"] = "google_shopping"
        else:
            item["link_type"] = "direct"

        item.pop("_score", None)

    _cache_set(cache_key, cleaned)
    return cleaned
