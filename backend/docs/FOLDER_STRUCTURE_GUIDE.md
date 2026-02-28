# Folder Structure Guide

Your TEST_RP workspace has been reorganized with the recommended team-ready folder structure. Here's what changed:

## 📋 New Structure Overview

```
c:\TEST_RP\
├── apps/
│   └── fashion-assistant/           ← Your component
│       ├── backend/                 ← Moved from src/
│       │   ├── agents/              ← AI agents (7 files)
│       │   ├── api/                 ← REST API endpoints
│       │   ├── ml_models/           ← ML models & embeddings
│       │   ├── ingestion/           ← Data preprocessing
│       │   ├── users/               ← User management
│       │   ├── utils/               ← Utility functions
│       │   ├── clients/             ← External API clients
│       │   ├── requirements.txt     ← Python dependencies
│       │   └── __init__.py
│       ├── frontend/                ← React app (moved from /frontend)
│       │   ├── src/
│       │   ├── public/
│       │   ├── package.json
│       │   └── tsconfig.json
│       ├── data/                    ← Datasets and embeddings
│       │   ├── raw/                 ← Original CSV files
│       │   ├── processed/           ← Cleaned data
│       │   └── embeddings_cache/    ← Cached embeddings
│       ├── Dockerfile.backend       ← Docker for backend
│       ├── Dockerfile.frontend      ← Docker for frontend
│       ├── .env.example             ← Environment template
│       └── README.md                ← Component documentation
│
├── services/                         ← Team member services
│   ├── data-mesh/                   ← [Team Member 1]
│   ├── data-fabric/                 ← [Team Member 2]
│   └── data-architecture/           ← [Team Member 3]
│
├── shared/                           ← Shared code across services
│   ├── auth/                        ← Authentication
│   ├── logging/                     ← Logging configuration
│   └── utils/                       ← Common utilities
│
├── infrastructure/                   ← Deployment & DevOps
│   ├── docker/
│   │   ├── docker-compose.yml       ← Orchestrate 6 services
│   │   └── .dockerignore
│   └── nginx/
│       └── nginx.conf               ← Reverse proxy config
│
├── docs/                             ← Documentation
│   ├── API_CONTRACTS.md             ← API specification
│   ├── ARCHITECTURE.md              ← System design
│   ├── SETUP.md                     ← Setup instructions
│   └── INTEGRATION_TESTING.md       ← Test guidelines
│
├── tests/                            ← Integration tests
│   └── e2e/                         ← End-to-end tests
│
├── docker-compose.yml               ← Main compose file
├── .env.example                     ← Environment template
├── .gitignore                       ← Git ignore rules
└── README.md                        ← Project documentation
```

## 🔄 Moved Files

### From `src/` → `apps/fashion-assistant/backend/`
- ✅ `agents/` - All 7 agent files
- ✅ `api/` - FastAPI endpoints
- ✅ `ml_models/` - Model files
- ✅ `ingestion/` - Data pipeline
- ✅ `users/` - User management
- ✅ `utils/` - Utilities
- ✅ `clients/` - External clients

### From `frontend/` → `apps/fashion-assistant/frontend/`
- ✅ React application files
- ✅ `src/` folder
- ✅ `public/` folder
- ✅ `package.json`
- ✅ All configuration files

### From `data/` → `apps/fashion-assistant/data/`
- ✅ `raw/` - Original datasets
- ✅ `processed/` - Cleaned datasets
- ✅ Embeddings cache

### Infrastructure Files
- ✅ `docker-compose.yml` → `infrastructure/docker/`
- ✅ `Dockerfile.backend` → `apps/fashion-assistant/`
- ✅ `Dockerfile.frontend` → `apps/fashion-assistant/`
- ✅ `nginx.conf` → `infrastructure/nginx/`

## 📝 Configuration Files

### `.env.example` (Root Level)
Contains all environment variables for:
- PostgreSQL configuration
- Redis configuration
- All 3 services configuration
- Frontend configuration
- Security settings

### `.env.example` (App Level)
Contains app-specific configuration:
- Backend settings
- Model configuration
- API configuration
- Frontend configuration

## 🎯 Benefits of This Structure

1. **Clear Separation** - Your code isolated in `apps/fashion-assistant/`
2. **Team Ready** - Services folder for team members
3. **Shared Resources** - `shared/` for common code
4. **Scalability** - Easy to add more services
5. **Docker Ready** - All services in docker-compose
6. **Documentation** - Dedicated `docs/` folder
7. **Testing** - Dedicated `tests/` folder
8. **Deployment Ready** - Infrastructure folder for DevOps

## 📍 Important File Locations

| What | Where |
|------|-------|
| Python code | `apps/fashion-assistant/backend/` |
| React code | `apps/fashion-assistant/frontend/src/` |
| AI agents | `apps/fashion-assistant/backend/agents/` |
| API endpoints | `apps/fashion-assistant/backend/api/` |
| Data files | `apps/fashion-assistant/data/` |
| Docker configs | `infrastructure/docker/` |
| Documentation | `docs/` |
| Environment vars | `.env.example` |
| Tests | `tests/e2e/` |

## 🚀 Next Steps

1. **Review** this structure
2. **Check** that all files are in correct locations
3. **Update** any import statements if needed
4. **Test** docker-compose.yml works
5. **Share** with team members
6. **Push** to GitHub/GitLab

## ⚙️ Working with the New Structure

### Backend Development
```bash
cd apps/fashion-assistant/backend
pip install -r requirements.txt
python -m src.api.app  # Run FastAPI server
```

### Frontend Development
```bash
cd apps/fashion-assistant/frontend
npm install
npm run dev  # Run Vite dev server
```

### Using Docker
```bash
docker-compose up -d           # Start all 6 services
docker-compose exec fashion-assistant-backend bash  # Enter container
docker-compose logs -f fashion-assistant-backend  # View logs
```

## 🔗 Related Documents

- See **README.md** for complete project overview
- See **MIGRATION_GUIDE.md** for how to migrate to team repo
- See **docs/API_CONTRACTS.md** for API specification
- See **docs/ARCHITECTURE.md** for system design

---

**Status:** ✅ Structure ready for team collaboration
**Last Updated:** February 28, 2026
