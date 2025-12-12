// frontend/src/App.js
import React, { useState } from "react";

const DEFAULT_API_BASE = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

export default function App() {
  const [query, setQuery] = useState("");
  const [maxResults, setMaxResults] = useState(6);
  const [loading, setLoading] = useState(false);
  const [products, setProducts] = useState([]);
  const [error, setError] = useState(null);
  const [useMock, setUseMock] = useState(false);

  const apiEndpoint = (useMock ? `${DEFAULT_API_BASE}/products/mock` : `${DEFAULT_API_BASE}/products/`);

  async function handleSubmit(e) {
    e && e.preventDefault();
    if (!query.trim()) {
      setError("Please enter a search query.");
      return;
    }

    setLoading(true);
    setError(null);
    setProducts([]);

    try {
      const res = await fetch(apiEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          query: query.trim(),
          max_results: Number(maxResults) || 6,
        }),
      });

      if (!res.ok) {
        // Try to parse JSON error message
        let text;
        try {
          const json = await res.json();
          text = json.detail || JSON.stringify(json);
        } catch {
          text = `${res.status} ${res.statusText}`;
        }
        throw new Error(text);
      }

      const data = await res.json();
      // API returns { query, total_results, products: [...] }
      setProducts(Array.isArray(data.products) ? data.products : []);
    } catch (err) {
      setError(err.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-3xl mx-auto">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold text-gray-800">Product Search</h1>
          <p className="text-sm text-gray-500 mt-1">Enter a product name (e.g. <code>Samsung s24</code>) and press Search.</p>
        </header>

        <form onSubmit={handleSubmit} className="bg-white p-4 rounded-lg shadow-sm flex flex-col gap-3">
          <div className="flex gap-3 items-center">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search products (e.g. Samsung s24)"
              className="flex-1 px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />

            <input
              type="number"
              min="1"
              max="50"
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
              title="Max results (1-50)"
              className="w-24 px-3 py-2 border rounded-md text-sm"
            />

            <button
              type="submit"
              disabled={loading}
              className={`px-4 py-2 rounded-md text-white ${loading ? "bg-indigo-300" : "bg-indigo-600 hover:bg-indigo-700"}`}
            >
              {loading ? "Searching..." : "Search"}
            </button>
          </div>

          <div className="flex items-center gap-3 text-sm">
            <label className="inline-flex items-center gap-2 text-gray-600">
              <input type="checkbox" checked={useMock} onChange={(e) => setUseMock(e.target.checked)} className="w-4 h-4" />
              Use mock endpoint (no API key)
            </label>

            <span className="text-gray-400">|</span>
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setProducts([]);
                setError(null);
              }}
              className="text-sm text-gray-600 hover:underline"
            >
              Clear
            </button>
          </div>
        </form>

        <main className="mt-6">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-md">
              <strong>Error:</strong> {error}
            </div>
          )}

          {!error && !loading && products.length === 0 && (
            <div className="text-gray-500">No results yet. Enter a query and press Search.</div>
          )}

          {products.length > 0 && (
            <div className="mt-4 grid gap-4">
              {products.map((p, idx) => (
                <article key={p.link || `${idx}-${p.title}`} className="bg-white p-4 rounded-lg shadow-sm flex gap-4 items-start">
                  <img
                    src={p.image || "https://via.placeholder.com/96x96?text=No+Image"}
                    alt={p.title}
                    className="w-24 h-24 object-cover rounded-md border"
                  />
                  <div className="flex-1">
                    <a href={p.link || "#"} target="_blank" rel="noopener noreferrer" className="text-lg font-medium text-indigo-600 hover:underline">
                      {p.title}
                    </a>

                    <div className="mt-2 flex items-center justify-between gap-4">
                      <div>
                        <div className="text-sm text-gray-600">Price</div>
                        <div className="text-base font-semibold">{p.price_raw ?? (p.price ? `₹${p.price}` : "—")}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm text-gray-600">Rating</div>
                        <div className="text-base">{p.rating ? p.rating.toFixed(1) : "—"}</div>
                        <div className="text-xs text-gray-400 mt-1">{p.source}</div>
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}

          {loading && (
            <div className="mt-4 text-gray-600">Searching — this may take a few seconds...</div>
          )}
        </main>

        <footer className="mt-8 text-xs text-gray-400">
          <div>Backend: {DEFAULT_API_BASE}/products/</div>
          <div className="mt-2">Tip: if CORS errors occur, confirm your FastAPI has CORS allowed for your frontend origin.</div>
        </footer>
      </div>
    </div>
  );
}
