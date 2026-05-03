# Fashion Catalog Assistant (Frontend)

React + TypeScript + Vite frontend for the fashion-aware search and chat experience powered by the custom embedding model and orchestrator backend.

## What’s here
- Chat search wired to backend POST /api/answer (uses fashion-optimized embeddings + intent + conversation memory).
- Product listings with color display and cart actions (add, remove, clear).
- API base auto-detected: `VITE_API_URL` env or `/api` proxy to backend.
- Styling: base Vite/React setup; easily skinnable.

## Running locally
1) Backend APIs (from `c:\Test\backend`):
   - Agentic AI API (`8000`): `& ".\.venv\Scripts\python.exe" -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload`
   - Data Mesh API (`8001`): `& ".\.venv\Scripts\python.exe" -m uvicorn src.services.data_mesh:app --host 127.0.0.1 --port 8001 --reload`
   - Data Fabric API (`8002`, optional): from `c:\Test\backend\src\services\data_fabric` run `& "c:\Test\backend\.venv\Scripts\python.exe" -m uvicorn src.api.main:app --host 127.0.0.1 --port 8002 --reload`
2) Frontend:
   - `cd frontend`
   - `npm install`
   - **Local:** `cp .env.example .env.local` and run `npm run dev`.
   - **Vercel (HTTPS):** do **not** point `VITE_*` at `http://` Azure IPs (browsers block mixed content). Use **`frontend/vercel.json`** rewrites + env values from **`.env.vercel.example`** (same-origin `/re/...` paths). Set those `VITE_*` variables in the Vercel project, commit `vercel.json`, and **Redeploy**. When Azure IPs change, edit **`frontend/vercel.json`** and redeploy.

## Quick API reference (used by this UI)
- POST /api/answer – main chat + search (fashion model, intent classifier, conversation memory).
- GET /api/search – product search.
- GET /api/products/{id} and /api/products/{id}/similar – product detail + similar items.
- Cart: POST /api/cart/add, GET /api/cart, DELETE /api/cart/clear, DELETE /api/cart/item/{index}.

## How it works (frontend → backend)
- UI sends user text to /api/answer → orchestrator → fashion embedding model → vector search results returned.
- Cart actions call cart endpoints; product detail/similar use dedicated endpoints.
- CORS is enabled in backend; Vite dev server proxies `/api` to http://localhost:8000.

## Future improvements
- Add UI surfacing of ranked reasons (why each item matched).
- Inline facets (price sliders, colors, fits) driven by the model’s extracted attributes.
- Streaming responses for chat for faster perceived latency.
- Lightweight analytics panel for query quality and fallback monitoring.
