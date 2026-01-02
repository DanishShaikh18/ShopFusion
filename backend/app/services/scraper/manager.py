# backend/app/services/scraper/manager.py
from __future__ import annotations

import os
import time
import logging
import math
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())


from .. import scraper_india  # fallback if you prefer calling directly
from .amazon_scraper import search_amazon
from .google_shopping_scraper import search_google_shopping

logger = logging.getLogger(__name__)

# Simple in-memory TTL cache
_CACHE: Dict[str, Tuple[float, List[Dict]]] = {}
CACHE_TTL_SECONDS = 60  # tune: 60 seconds for dev

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

def _normalize_title_for_key(title: str) -> str:
    if not title:
        return ""
    s = title.lower()
    s = "".join(ch if ch.isalnum() else " " for ch in s)
    return " ".join(s.split())

def _dedupe_and_merge(items: List[Dict], max_results: int) -> List[Dict]:
    """
    Deduplicate by normalized title and link. Keep the best-scoring entry for each group.
    """
    groups = {}
    for it in items:
        key_candidates = []
        title_key = _normalize_title_for_key(it.get("title") or "")
        if it.get("link"):
            key_candidates.append(it.get("link"))
        if title_key:
            key_candidates.append(title_key[:120])  # limit key length
        # choose first key candidate as group key
        if not key_candidates:
            continue
        gk = key_candidates[0]
        if gk not in groups:
            groups[gk] = it
        else:
            # merge: prefer lower price if available, or higher rating
            existing = groups[gk]
            # pick cheaper if both have price
            p_new = it.get("price")
            p_old = existing.get("price")
            if p_new is not None and p_old is not None:
                if p_new < p_old:
                    groups[gk] = it
            else:
                # fallback to rating
                r_new = it.get("rating") or 0
                r_old = existing.get("rating") or 0
                if r_new > r_old:
                    groups[gk] = it

    out = list(groups.values())
    # simple sorting: prefer items with price (low), higher rating
    out.sort(key=lambda x: ((x.get("price") is None), x.get("price") or math.inf, -(x.get("rating") or 0.0)))
    return out[:max_results]

def _score_item_brand_model(item: Dict, query: str) -> float:
    """
    Lightweight scoring: brand presence and model token match (simple heuristics).
    Returns score in 0..1
    """
    q = query.lower()
    title = (item.get("title") or "").lower()
    score = 0.0
    # exact tokens
    for tok in q.split():
        if tok and tok in title:
            score += 0.2
    # small bonus for rating and price present
    if item.get("rating"):
        score += 0.15
    if item.get("price") is not None:
        score += 0.1
    return min(score, 1.0)

def search_all(query: str, max_results: int = 6, sources: Optional[List[str]] = None, api_key: Optional[str] = None) -> List[Dict]:
    """
    Orchestrator: call multiple scrapers, merge/dedupe, score, and return top results.
    sources: list of strings: "amazon", "google_shopping" etc. Default: both.
    """
    if not sources:
        sources = ["amazon", "google_shopping"]

    # simple cache key
    cache_key = f"{query}::{'|'.join(sources)}::{max_results}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("manager: cache hit for %s", cache_key)
        return cached

    api_key = api_key or os.getenv("SERPAPI_KEY")  # use env key if present

    candidates = []
    # call scrapers (sequential for simplicity). You can call them in parallel later.
    if "amazon" in sources:
        try:
            candidates.extend(search_amazon(query=query, max_results=max_results, api_key=api_key))
        except Exception as exc:
            logger.warning("amazon scraper failed: %s", exc)

    if "google_shopping" in sources:
        try:
            candidates.extend(search_google_shopping(api_key=api_key, query=query, max_results=max_results))
        except Exception as exc:
            logger.warning("google_shopping scraper failed: %s", exc)

    # If nothing found, return empty list
    if not candidates:
        _cache_set(cache_key, [])
        return []

    # score each candidate relative to query
    for it in candidates:
        it["_score"] = _score_item_brand_model(it, query)

    # sort candidates by score desc then price asc then rating desc
    candidates.sort(key=lambda x: (-(x.get("_score") or 0.0), (x.get("price") or float("inf")), -(x.get("rating") or 0.0)))

    # dedupe/merge and limit
    final = _dedupe_and_merge(candidates, max_results=max_results)

    # clear internal keys before returning
    for it in final:
        it.pop("_score", None)
    _cache_set(cache_key, final)
    return final
