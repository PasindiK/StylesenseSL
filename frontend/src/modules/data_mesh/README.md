# Data Mesh Frontend Module

This module contains the standalone Data Mesh Control Plane UI.

## Run locally

```bash
npm --prefix frontend/src/modules/data_mesh install
npm --prefix frontend/src/modules/data_mesh run dev -- --host 127.0.0.1 --port 5174
```

Build:

```bash
npm --prefix frontend/src/modules/data_mesh run build
```

## API target

Frontend calls are configured in `src/config.js`.

Default:

- `API_BASE = http://localhost:8001`

## Governance evaluation utility

The Pipeline Monitoring page includes an upload-based admin control:

- **Panel title:** `Governance Evaluation Test Cases`
- **Action:** upload a domain CSV to replace the mapped Silver file and rerun the existing pipeline

## Backend dependency (required)

The upload endpoint requires multipart parsing support in the backend environment.

- Ensure `python-multipart` is installed via `backend/requirements.txt`
- If missing, FastAPI upload routes can fail at startup/runtime

## Backend endpoint used by utility

- `POST /admin/governance-test-cases/upload-and-rerun`

Expected multipart form fields:

- `file` (CSV)
- `session_id`
- `user_id`
- `auth_username`
- `auth_password`

File/domain mapping behavior:

- Filename is used to infer target domain/file (for example `sales_*.csv`, `users_*.csv`)
- Matched Silver file is overwritten (replace behavior, no append)
- Existing pipeline rerun and governance refresh execute unchanged

Summary response includes:

- uploaded filename
- mapped domain
- replaced Silver file
- rerun success/failure
- latest governance refresh time
