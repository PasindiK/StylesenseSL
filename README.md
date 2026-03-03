# StyleSense Solution

StyleSense is a Python + React platform for fashion intelligence, combining data architecture, data mesh, data fabric, and agentic AI to deliver analytics, recommendations, and operational insights.

This repository is **not** a Spring Boot application.

## Simple Lakehouse Architecture (Short Overview)

StyleSense follows a practical lakehouse pattern:
- **Raw zone**: source files and ingested datasets (users, products, shops, sales, interactions)
- **Processed zone**: cleaned and transformed datasets for analytics and ML
- **Serving zone**: APIs, dashboards, and agents consume trusted domain data

This keeps storage flexible like a data lake while supporting structured analytics and application use like a warehouse.

## Core Platform Features

### 1) Data Architecture
- Organizes datasets into clear layers (`raw` → `processed` → serving)
- Standardizes schemas and data contracts for consistent downstream use
- Supports scalable onboarding of new fashion and commerce datasets

### 2) Data Mesh
- Domain-oriented data ownership (users, products, sales, shops, engagement)
- Independent domain data products with health and governance visibility
- Dedicated UI and backend for mesh monitoring and contract-aware operations

### 3) Data Fabric
- Connects and harmonizes data services across domains and modules
- Improves discoverability, reuse, and interoperability of data assets
- Provides shared patterns for integration, quality checks, and access

### 4) Agentic AI
- AI agents for catalog intelligence, user understanding, and automation flows
- Scripted entry points and backend modules for agent execution
- Designed to work with mesh/fabric data for contextual decision support

## Current Project Structure

- `backend/`
  - `src/services/agentic_ai/` (agents, scripts, requirements)
  - `src/services/data_mesh/` (backend API, data, requirements)
  - `src/services/data_fabric/`
  - `src/services/data_architecture/`
  - `src/shared/` (shared constants, enums, models, utils)
- `frontend/`
  - `src/modules/agentic_ai/`
  - `src/modules/data_mesh/` (standalone module app files)
  - `src/modules/data_fabric/`
  - `src/modules/data_architecture/`
  - `src/shared/`
- `docker/`

## Prerequisites

- Python 3.10+ (recommended for backend services)
- Node.js 20+ and npm 10+ (recommended for frontend apps)
- Windows PowerShell commands are shown below

## Run Commands

### 1) Agentic AI Backend API (port 8000)
```powershell
cd c:\Test\backend
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

### 2) Data Mesh Backend API (port 8001)
```powershell
cd c:\Test\backend
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -r src\services\data_mesh\requirements.txt
& ".\.venv\Scripts\python.exe" -m uvicorn src.services.data_mesh:app --host 127.0.0.1 --port 8001 --reload
```

### 3) Data Fabric Backend API (port 8002)
```powershell
cd c:\Test\backend\src\services\data_fabric
& "c:\Test\backend\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& "c:\Test\backend\.venv\Scripts\python.exe" -m uvicorn src.api.main:app --host 127.0.0.1 --port 8002 --reload
```

### 4) Main Frontend App (port 5173)
```powershell
cd c:\Test\frontend
npm install
npm run dev -- --port 5173
```

### 5) Data Mesh Frontend Module (port 5174)
```powershell
cd c:\Test\frontend\src\modules\data_mesh
npm install
npm run dev -- --port 5174
```

## Quick Health Checks

- Agentic AI backend docs: `http://127.0.0.1:8000/docs`
- Data Mesh health: `http://127.0.0.1:8001/health`
- Data Fabric docs: `http://127.0.0.1:8002/api/docs`

## Notes

- `frontend/src/modules/data_architecture` and `frontend/src/modules/data_fabric` are prepared as module folders; add app files there when those UIs are implemented.
- `backend/src/services/data_architecture` is prepared as a backend service folder; add API entrypoint before running it as a standalone service.

## Troubleshooting

- In PowerShell, use `&` when running the venv Python executable.
- Use `.\.venv\...` (current folder) — **not** `..venv\...`.
- If you want the black landing/chat UI with tile button, run **Main Frontend App** on `http://localhost:5173`.
- `http://localhost:5174` is the **Data Mesh module UI**, which is a different frontend.
