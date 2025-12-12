# scraper_india.py
from __future__ import annotations

import os
import re
import time
import logging
from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

# Attempt to auto-find & load a .env (searches upwards from cwd)
_dotenv_path = find_dotenv()
if _dotenv_path:
    load_dotenv(_dotenv_path)
else:
    # fallback: attempt to load default behaviour (no path)
    load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_DOMAIN = "amazon.in"
RETRIES = 3
RETRY_SLEEP_SECONDS = 1.0
_PRICE_RE = re.compile(r"[\d,.]+")


def _get_api_key(cli_key: Optional[str] = None) -> str:
    """Return SERPAPI_KEY from cli override or environment. Raises RuntimeError if missing."""
    key = cli_key or os.getenv("SERPAPI_KEY")
    if key:
        # strip optional surrounding quotes
        if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
            key = key[1:-1]
    if not key:
        raise RuntimeError(
            "SERPAPI_KEY not found. Place SERPAPI_KEY=your_key in a .env or set the environment variable."
        )
    return key


def _fetch_serpapi_results(api_key: str, query: str, amazon_domain: str = DEFAULT_DOMAIN, params_extra: Optional[dict] = None) -> Dict[str, Any]:
    """Call SerpAPI (google-search-results package) and return response dict."""
    try:
        from serpapi import GoogleSearch  # type: ignore
    except Exception as exc:
        raise RuntimeError("Missing dependency 'serpapi' (install with: pip install google-search-results)") from exc

    params = {
        "engine": "amazon",
        "k": query,
        "amazon_domain": amazon_domain,
        "api_key": api_key,
    }
    if params_extra:
        params.update(params_extra)

    last_exc: Optional[BaseException] = None
    for attempt in range(1, RETRIES + 1):
        try:
            logger.debug("SerpAPI request attempt %d for query=%s", attempt, query)
            search = GoogleSearch(params)
            data = search.get_dict()
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            last_exc = exc
            logger.warning("SerpAPI attempt %d failed: %s", attempt, exc)
            if attempt < RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS * attempt)
            else:
                raise RuntimeError("SerpAPI request failed after retries") from last_exc
    raise RuntimeError("SerpAPI request failed (unknown reason)")


def _parse_price(value: Optional[Any]) -> Optional[float]:
    if value is None:
        return None
    m = _PRICE_RE.search(str(value))
    if not m:
        return None
    cleaned = m.group(0).replace(",", "")
    try:
        return float(cleaned)
    except Exception:
        return None


def _simple_normalize_text(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower()
    # replace non-alphanum with single space, trim
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _title_contains_tokens(title: str, tokens: List[str]) -> bool:
    t = _simple_normalize_text(title).split()
    token_set = set(tokens)
    return token_set.issubset(set(t))


def _fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _is_sponsored(item: Dict[str, Any]) -> bool:
    # heuristics: SerpAPI may mark sponsored results with keys like 'sponsored', 'is_ad', or similar
    for k in ("sponsored", "is_ad", "ad", "ads"):
        if item.get(k):
            return True
    # also some sponsored items have 'ad' or 'sponsored' in the title or snippet
    title = str(item.get("title") or item.get("name") or "")
    if "sponsored" in title.lower() or "ad -" in title.lower() or title.lower().startswith("ad "):
        return True
    return False


def _extract_candidates_from_response(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Pull candidate product-like dictionaries from common SerpAPI keys.
    Keeps the raw dicts so we can examine fields for sponsored flag etc.
    """
    candidates: List[Dict[str, Any]] = []
    keys_to_check = ("products", "shopping_results", "organic_results", "inline_products", "product_results", "amazon_products")
    for k in keys_to_check:
        v = raw.get(k)
        if isinstance(v, list):
            candidates.extend(v)

    # fallback: include any top-level lists of dicts
    if not candidates:
        for v in raw.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                candidates.extend(v)

    return candidates


def _normalize_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None

    title = item.get("title") or item.get("name") or item.get("product_title") or item.get("title_raw")
    link = item.get("link") or item.get("product_link") or item.get("url") or item.get("product_url")
    if not title and not link:
        return None

    price_raw = item.get("price") or item.get("price_raw") or item.get("displayed_price") or item.get("formatted_price")
    price = _parse_price(price_raw)
    image = item.get("thumbnail") or item.get("image") or item.get("image_src")
    rating = None
    for rk in ("rating", "reviews_rating", "rating_value"):
        if rk in item:
            try:
                rating = float(item[rk])
                break
            except Exception:
                rating = None

    return {
        "title": title,
        "price_raw": str(price_raw) if price_raw is not None else None,
        "price": price,
        "link": link,
        "image": image,
        "rating": rating,
        "source": "Amazon (SerpAPI)",
        "_raw": item,
    }


def _score_item_for_query(normalized_title: str, brand_tokens: List[str], model_tokens: List[str]) -> float:
    """
    Score an item based on brand presence (high-weight) and model similarity.
    Returns score in 0..1 range (not strictly bounded but used for ranking).
    """
    title_norm = _simple_normalize_text(normalized_title)

    # brand presence = binary (require brand to be present for any reasonable score)
    brand_present = 1 if any(bt in title_norm.split() for bt in brand_tokens) else 0

    # model presence: check tokens substring first
    model_present = 1 if any(mt in title_norm.split() for mt in model_tokens) else 0

    # fuzzy score: compare normalized title with joined model tokens
    model_joined = " ".join(model_tokens)
    fuzzy = _fuzzy_ratio(title_norm, model_joined) if model_tokens else 0.0

    # weighted score (brand mandatory, but allow fuzzy to help rank)
    # if brand not present, give a small penalty but allow fuzzy to salvage (tunable)
    score = 0.0
    score += 0.65 * brand_present
    # prefer direct model presence
    score += 0.25 * model_present
    # fuzzy supplement
    score += 0.10 * fuzzy
    return score


def search(query: str, max_results: int = 6, api_key: Optional[str] = None, amazon_domain: str = DEFAULT_DOMAIN, params_extra: Optional[dict] = None, verbose: bool = False) -> List[Dict[str, Any]]:
    """
    Synchronous search function intended to be called inside a thread (asyncio.to_thread).
    Returns a list of normalized product dicts filtered and ranked to match brand+model queries better.
    """
    if verbose:
        logger.info("scraper_india.search query=%s max_results=%d domain=%s", query, max_results, amazon_domain)

    api_key = _get_api_key(api_key)
    raw = _fetch_serpapi_results(api_key=api_key, query=query, amazon_domain=amazon_domain, params_extra=params_extra)

    # Extract brand and model tokens from the query
    q_norm = _simple_normalize_text(query)
    q_tokens = [t for t in q_norm.split() if len(t) > 0]
    # heuristics: treat first token as brand if there are multiple tokens
    brand_tokens = [q_tokens[0]] if len(q_tokens) >= 1 else []
    # remaining tokens are model (if any)
    model_tokens = q_tokens[1:] if len(q_tokens) > 1 else []

    candidates = _extract_candidates_from_response(raw)

    normalized_items: List[Dict[str, Any]] = []
    for raw_item in candidates:
        # skip obvious ads/sponsored heuristically
        if _is_sponsored(raw_item):
            continue
        normalized = _normalize_item(raw_item)
        if not normalized:
            continue
        normalized_items.append(normalized)

    # compute scores and sort
    scored: List[Dict[str, Any]] = []
    for it in normalized_items:
        title = it["title"] or ""
        score = _score_item_for_query(title, brand_tokens, model_tokens)
        it["_score"] = score
        scored.append(it)

    # sort descending by score, tie-breaker by price (cheap first) then rating
    scored.sort(key=lambda x: (x.get("_score", 0.0), -(x.get("rating") or 0.0), - (x.get("price") or 0.0)), reverse=True)

    # If brand token is present in query, filter out items with extremely low scores
    if brand_tokens:
        scored = [s for s in scored if s.get("_score", 0.0) >= 0.35]  # threshold tuned for brand+model queries

    # If not enough matches, relax filter (allow lower score)
    if len(scored) < max_results:
        # fallback: include normalized_items not already in scored, with lower cutoff
        remaining = [it for it in normalized_items if it not in scored]
        for it in remaining:
            it["_score"] = _score_item_for_query(it["title"] or "", brand_tokens, model_tokens)
            scored.append(it)

        scored.sort(key=lambda x: x.get("_score", 0.0), reverse=True)

    # limit results and strip internal _raw/_score fields from public output if you prefer
    result = []
    for item in scored[:max_results]:
        # return a copy without heavy _raw internal data (but keep it for debugging if you want)
        out = {
            "title": item.get("title"),
            "price_raw": item.get("price_raw"),
            "price": item.get("price"),
            "link": item.get("link"),
            "image": item.get("image"),
            "rating": item.get("rating"),
            "source": item.get("source"),
        }
        result.append(out)

    return result
