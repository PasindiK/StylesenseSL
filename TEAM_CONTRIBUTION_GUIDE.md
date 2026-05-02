# Team Contribution Guide (Backend + Frontend Separation)

## Goal
Allow each team member to add code independently without breaking other components.

## Required Structure

- `apps/agentic-ai/` → main user-facing application (chatbot backend + frontend)
- `services/data-mesh/backend/` → Data Mesh backend code
- `services/data-mesh/frontend/` → Data Mesh frontend code (optional)
- `services/data-fabric/backend/` → Data Fabric backend code
- `services/data-fabric/frontend/` → Data Fabric frontend code (optional, but supported)
- `services/data-architecture/backend/` → Data Architecture backend code
- `services/data-architecture/frontend/` → Data Architecture frontend code (optional)

## Team Rules

1. **Do not put service code in other service folders.**
2. **Each service owns its own backend and frontend folders.**
3. **Never hardcode URLs**; use env variables.
4. **Do not change another team’s API contract without discussion.**
5. **Keep each service independently runnable.**

## API & Port Convention

- Agentic AI backend: `8000`
- Data Mesh backend: `8001`
- Data Fabric backend: `8002`
- Data Architecture backend: `8003`

Frontend apps should each run on their own dev ports (e.g. 5173, 5174, 5175).

## What to Tell New Team Members

- Add backend files only under your service's `backend/`.
- Add frontend files only under your service's `frontend/`.
- Expose backend APIs with clear endpoint docs.
- Add `.env.example` inside your service/frontend/backend as needed.
- Open PRs with scoped changes (only your service unless cross-service contract update).

## Frontend Guidance

- Keep Agentic AI frontend in `apps/agentic-ai/frontend/` as the main product UI.
- Add service-specific frontends only if needed for monitoring/admin/debug workflows.
- If a service does not need a UI, keep `frontend/` minimal with a README.

## Suggested Branch Naming

- `feat/data-fabric-<topic>`
- `feat/data-mesh-<topic>`
- `feat/data-architecture-<topic>`
- `feat/agentic-ai-<topic>`

## Minimum PR Checklist

- [ ] Code added only in correct service folder
- [ ] `.env.example` updated if new config added
- [ ] API endpoints documented
- [ ] Local run steps verified
- [ ] No unrelated file changes
