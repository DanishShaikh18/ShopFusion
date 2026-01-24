// frontend/src/App.js
import React, { useState } from "react";

const API_BASE = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

export default function App() {
  const [query, setQuery] = useState("");
  const [maxResults, setMaxResults] = useState(6);
  const [loading, setLoading] = useState(false);
  const [products, setProducts] = useState([]);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();

    if (!query.trim()) {
      setError("Please enter a product name.");
      return;
    }

    setLoading(true);
    setError(null);
    setProducts([]);

    try {
      const res = await fetch(`${API_BASE}/products/`, {
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
        let message;
        try {
          const json = await res.json();
          message = json.detail || "Request failed";
        } catch {
          message = `${res.status} ${res.statusText}`;
        }
        throw new Error(message);
      }

      const data = await res.json();
      setProducts(Array.isArray(data.products) ? data.products : []);
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-3xl mx-auto">
        {/* HEADER */}
        <header className="mb-6">
          <h1 className="text-2xl font-semibold text-gray-800">
            Smart Product Search
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Clean, relevant results with an automatic best recommendation.
          </p>
        </header>

        {/* SEARCH FORM */}
        <form
          onSubmit={handleSubmit}
          className="bg-white p-4 rounded-lg shadow-sm flex flex-col gap-3"
        >
          <div className="flex gap-3 items-center">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Samsung Galaxy S24"
              className="flex-1 px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />

            <input
              type="number"
              min="1"
              max="20"
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
              className="w-24 px-3 py-2 border rounded-md text-sm"
            />

            <button
              type="submit"
              disabled={loading}
              className={`px-4 py-2 rounded-md text-white ${
                loading
                  ? "bg-indigo-300"
                  : "bg-indigo-600 hover:bg-indigo-700"
              }`}
            >
              {loading ? "Searching..." : "Search"}
            </button>
          </div>

          <button
            type="button"
            onClick={() => {
              setQuery("");
              setProducts([]);
              setError(null);
            }}
            className="self-start text-sm text-gray-600 hover:underline"
          >
            Clear results
          </button>
        </form>

        {/* RESULTS */}
        <main className="mt-6">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded-md">
              <strong>Error:</strong> {error}
            </div>
          )}

          {!loading && !error && products.length === 0 && (
            <div className="text-gray-500">
              No results yet. Try searching for a product.
            </div>
          )}

          {products.length > 0 && (
            <div className="grid gap-4">
              {products.map((p, idx) => (
                <article
                  key={p.link || `${idx}-${p.title}`}
                  className={`bg-white p-4 rounded-lg shadow-sm flex gap-4 items-start border ${
                    p.is_recommended
                      ? "border-green-500"
                      : "border-transparent"
                  }`}
                >
                  <img
                    src={
                      p.image ||
                      "https://via.placeholder.com/96x96?text=No+Image"
                    }
                    alt={p.title}
                    className="w-24 h-24 object-cover rounded-md border"
                  />

                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <a
                        href={p.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-lg font-medium text-indigo-600 hover:underline"
                      >
                        {p.title}
                      </a>

                      {p.is_recommended && (
                        <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
                          ⭐ Recommended
                        </span>
                      )}
                    </div>

                    <div className="mt-2 flex justify-between gap-4">
                      <div>
                        <div className="text-sm text-gray-600">Price</div>
                        <div className="font-semibold">
                          {p.price_raw ??
                            (p.price ? `₹${p.price}` : "—")}
                        </div>
                      </div>

                      <div className="text-right">
                        <div className="text-sm text-gray-600">Rating</div>
                        <div>{p.rating ? p.rating.toFixed(1) : "—"}</div>
                        <div className="text-xs text-gray-400">
                          {p.source}
                        </div>
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}

          {loading && (
            <div className="mt-4 text-gray-600">
              Searching products… please wait.
            </div>
          )}
        </main>

        {/* FOOTER */}
        <footer className="mt-8 text-xs text-gray-400">
          Backend: {API_BASE}/products/
        </footer>
      </div>
    </div>
  );
}
