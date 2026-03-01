# Frontend Strategy

## Primary Frontend

- Main user-facing UI should stay in `apps/agentic-ai/frontend/`.

## Service Frontends

Service-level frontends are optional and should be used for:
- Admin screens
- Monitoring dashboards
- Data quality/validation tools
- Internal operational views

Locations:
- `services/data-mesh/frontend/`
- `services/data-fabric/frontend/`
- `services/data-architecture/frontend/`

## API URL Convention (Vite)

- `VITE_AGENTIC_API_URL=http://localhost:8000`
- `VITE_DATA_MESH_API_URL=http://localhost:8001`
- `VITE_DATA_FABRIC_API_URL=http://localhost:8002`
- `VITE_DATA_ARCH_API_URL=http://localhost:8003`

## Recommendation

If you want a simple team workflow:
- Keep one primary product frontend (`apps/agentic-ai/frontend`).
- Add service frontends only when there is a concrete UI need.
