"""
Minimal FastAPI application entrypoint for the Product Search API.

Notes:
- Keep this file intentionally small and focused: CORS, router inclusion, root and health endpoints.
- When running with uvicorn from the repository `backend` directory, use:
    python -m uvicorn app.main:app --reload
  (this ensures the `app` package is importable).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.api import product as product_router_module

app = FastAPI(title="Product Search API")

# Minimal CORS for development; tighten in production as needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register router (the main code lives in app/api/product.py)
app.include_router(product_router_module.router, prefix="/products", tags=["products"])


@app.get("/", summary="Root")
def root():
    return {"status": "ok", "routes": ["/products", "/products/mock"]}


@app.get("/health", summary="Health check")
def health():
    """
    Simple health check:
    - reports whether SERPAPI_KEY is loaded from environment (or .env),
    - and whether the optional `serpapi` client package is importable.
    """
    serpapi_key_present = bool(os.getenv("SERPAPI_KEY"))
    serpapi_installed = True
    serpapi_info = "present"
    try:
        import serpapi  # type: ignore
        serpapi_info = getattr(serpapi, "__file__", "module present")
    except Exception as exc:
        serpapi_installed = False
        serpapi_info = str(exc)

    return {
        "serpapi_installed": serpapi_installed,
        "serpapi_info": serpapi_info,
        "SERPAPI_KEY_loaded": serpapi_key_present,
    }
