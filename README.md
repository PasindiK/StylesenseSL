# StyleSenseSL

StyleSenseSL is an AI-powered fashion discovery platform with:
- a FastAPI backend for conversational product search, intent routing, personalization, and cart workflows,
- a React + Vite frontend for chat-first shopping UX,
- service modules for Data Mesh, Data Fabric, and Data Architecture expansion.

## Tech Stack

- **Backend:** Python, FastAPI, pandas, rapidfuzz, requests, ChromaDB, sentence-transformers
- **Frontend:** React 19, TypeScript, Vite, TailwindCSS, framer-motion
- **AI/ML:** semantic vector search + fashion-optimized embedding wrapper + Gemini-assisted intent/response utilities
- **Infra:** Docker + Docker Compose

## Repository Layout

```text
.
├─ backend/                     # Main API, agents, ingestion, user intelligence
│  ├─ src/
│  │  ├─ api/                   # FastAPI app + orchestrator routing
│  │  ├─ agents/                # Catalog, order, vector search, personalization agents
│  │  ├─ users/                 # User profile + preference extraction
│  │  ├─ ingestion/             # Dataset loading/parsing
│  │  └─ services/              # Additional service implementations (incl. data_fabric API)
│  ├─ data/                     # Raw + processed fashion datasets and embedding cache
│  └─ tests/                    # Unit/e2e-style backend tests
├─ frontend/                    # Main user-facing web app
├─ docker/                      # Compose + Dockerfiles for backend/frontend/nginx
├─ infrastructure/              # Infra scaffolding (compose/docker/k8s/terraform)
├─ services/                    # Team service workspaces (data-mesh/fabric/architecture)
└─ docs/
```

## Core Features

- Conversational query endpoint (`/api/answer`) with orchestrator-driven intent routing
- Product search (`/api/search`) and semantic similar product lookup (`/api/products/{id}/similar`)
- Personalization reranking using user interaction history and preference extraction
- Shopping cart APIs (add/view/update/remove/clear) backed by:
  - direct dataset URL-to-product lookup, and
  - fallback scraping for external product URLs
- Optional semantic vector search with cached embeddings under `backend/data/embeddings_cache/`

## Prerequisites

- Python **3.10+**
- Node.js **18+** (or newer LTS)
- npm
- (Optional) Docker Desktop

## Local Development

### 1) Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Backend health check:

```powershell
curl http://localhost:8000/api/health
```

### 2) Frontend

```powershell
cd frontend
npm install
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies `/api` to `http://localhost:8000`.

## Environment Configuration

Create `backend/.env` and set values like:
## Workspace Customization (Current Project)

- Runtime baseline validated on macOS in this workspace:
  - Agentic AI backend on `127.0.0.1:8000`
  - Main frontend on `127.0.0.1:5173`
  - Data Mesh backend on `127.0.0.1:8001`
- End-to-end synthetic time alignment workflow is available at:
  - `backend/src/services/data_mesh/src/time_alignment_governance_workflow.py`

Run it with:

```bash
/Users/nandunmadawa/Desktop/DATAMESHSTYLESENSESL/backend/.venv/bin/python \
  /Users/nandunmadawa/Desktop/DATAMESHSTYLESENSESL/backend/src/services/data_mesh/src/time_alignment_governance_workflow.py
```

This executes Silver-only business-date rebasing, reruns the Silver→Mesh pipeline, refreshes governance outputs, and prints a concise summary.

## Run Commands

```dotenv
GEMINI_API_KEY=your_key_here
GEMINI_MOCK=1
OPENAI_API_KEY=your_key_here
```

Notes:
- `GEMINI_MOCK=1` enables local mock behavior.
- Do **not** commit real API keys.
- If any key was previously committed, rotate it immediately.

## Run with Docker

From repository root:

```powershell
docker compose -f docker/docker-compose.yml up --build
```

Services (default):
- Agentic backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`
- Neo4j browser: `http://localhost:7474`

Optional Mesh / Fabric / Architecture APIs:

```powershell
docker compose -f docker/docker-compose.yml --profile microservices up --build
```

Dockerfiles live under `docker/backend/` (`Dockerfile.agentic`, `Dockerfile.data-mesh`, `Dockerfile.data-fabric`, `Dockerfile.data-architecture`).

## Main API Endpoints

- `GET /api/health` – service health
- `GET /api/search?q=...&limit=...` – catalog search
- `GET /api/products/{product_id}` – single product detail
- `GET /api/products/{product_id}/similar?limit=...` – similar products
- `GET /api/shops/{shop_id}` – shop info
- `GET /api/users` – user list (from users dataset)
- `POST /api/answer` – orchestrated conversational entry point
- `POST /api/cart/add` – add item by product URL (+ optional quantity/size)
- `GET /api/cart` – cart summary
- `PATCH /api/cart/item/{index}` – update item quantity
- `DELETE /api/cart/item/{index}` – remove one item
- `DELETE /api/cart/clear` – clear cart

## Data Dependencies

Expected input files are under `backend/data/raw/` (e.g. `final_products.csv`, `shops_dataset.csv`, `users_dataset.csv`).

The backend `DataLoader` resolves data using:
- `DATA_DIR` environment variable when provided, or
- default local path `backend/data`, or
- `/app/data` when running in container.

## Testing

Run backend tests:

```powershell
cd backend
pytest -q
```

## Service Modules (Team Structure)

The repo includes additional service workspaces under `services/` and code under `backend/src/services/` for:
- Data Mesh
- Data Fabric
- Data Architecture

Use these as independently evolvable components following `TEAM_CONTRIBUTION_GUIDE.md`.

## Known Notes

- This codebase currently contains a mix of active modules and scaffolding/placeholder modules.
- The main production path for this branch is the FastAPI backend in `backend/src/api/app.py` and the frontend in `frontend/`.
- Keep API contracts stable across team modules and prefer environment variables over hardcoded service URLs.
