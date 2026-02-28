# Migration Guide: Moving to Team Repository

## ✅ Yes, You Can Copy the Folder and It Will Work!

**Answer:** YES, copying your full folder to another location and pushing to git will work perfectly. Here's why:
- Git tracks files, not folder locations on your machine
- Your code doesn't have absolute path dependencies (uses relative paths)
- Environment variables in `.env` handle configuration
- You can develop both versions in parallel without issues

---

## 🎯 Recommended Approach: Parallel Development Strategy

### **Strategy: Keep Two Repositories**

```
C:\YOUR_MACHINE\
│
├── TEST_RP\                           # Original repo (your solo work)
│   └── (current structure)            # Continue developing here
│
└── team-data-platform\                # New team repo
    ├── apps\
    │   └── fashion-assistant\          # Your component (synced from TEST_RP)
    └── services\
        ├── data-mesh\
        ├── data-fabric\
        └── data-architecture\
```

**Benefits:**
✅ Keep your original work safe and independent  
✅ Experiment with integration without risk  
✅ Easy to sync changes between both  
✅ Can develop features independently, then merge  

---

## 📝 Step-by-Step Instructions

### **STEP 1: Create New Team Repository Structure**

```powershell
# Create team repo folder
cd C:\
mkdir team-data-platform
cd team-data-platform

# Initialize git
git init
git remote add origin <YOUR_TEAM_REPO_URL>

# Create folder structure
mkdir apps\fashion-assistant
mkdir services\data-mesh
mkdir services\data-fabric
mkdir services\data-architecture
mkdir shared\auth
mkdir shared\logging
mkdir shared\utils
mkdir infrastructure\docker
mkdir infrastructure\nginx
mkdir docs
mkdir tests\e2e

# Create README files
New-Item -Path "README.md" -ItemType File
New-Item -Path "apps\fashion-assistant\README.md" -ItemType File
New-Item -Path "services\data-mesh\README.md" -ItemType File
New-Item -Path "services\data-fabric\README.md" -ItemType File
New-Item -Path "services\data-architecture\README.md" -ItemType File
```

---

### **STEP 2: Copy Your Component (Safe Method)**

```powershell
# Navigate to team repo
cd C:\team-data-platform\apps\fashion-assistant

# Copy your entire TEST_RP content (EXCLUDING git history)
# Option A: Manual copy
xcopy C:\TEST_RP\* C:\team-data-platform\apps\fashion-assistant\ /E /I /EXCLUDE:C:\exclude.txt

# Create exclude.txt first (to avoid copying git, venv, etc.)
# In C:\exclude.txt, add:
# .git
# venv
# node_modules
# __pycache__
# .env
# *.pyc
# .pytest_cache

# Option B: Using robocopy (better, recommended)
robocopy C:\TEST_RP C:\team-data-platform\apps\fashion-assistant /E /XD .git venv node_modules __pycache__ .pytest_cache /XF *.pyc .env
```

---

### **STEP 3: Restructure Inside fashion-assistant/**

```powershell
cd C:\team-data-platform\apps\fashion-assistant

# Create new structure
mkdir backend
mkdir backend\agents
mkdir backend\api
mkdir backend\ml_models
mkdir backend\ingestion
mkdir backend\users
mkdir backend\utils

# Move files
Move-Item -Path "src\agents\*" -Destination "backend\agents\"
Move-Item -Path "src\api\*" -Destination "backend\api\"
Move-Item -Path "src\ml_models\*" -Destination "backend\ml_models\"
Move-Item -Path "src\ingestion\*" -Destination "backend\ingestion\"
Move-Item -Path "src\users\*" -Destination "backend\users\"
Move-Item -Path "src\utils\*" -Destination "backend\utils\"

# Copy requirements
Copy-Item "requirements.txt" -Destination "backend\requirements.txt"

# Remove old src folder (after verifying all files moved)
Remove-Item "src" -Recurse -Force

# Frontend stays as is
# frontend\ folder already exists and works
```

---

### **STEP 4: Update Import Paths in Code**

Your imports will need updating from `src.agents` to `backend.agents`:

**Before:**
```python
from src.agents.catalog_agent import CatalogAgent
from src.api.orchestrator import Orchestrator
```

**After:**
```python
from backend.agents.catalog_agent import CatalogAgent
from backend.api.orchestrator import Orchestrator
```

**Quick Fix Script** (save as `update_imports.py`):
```python
import os
import re

def update_imports(directory):
    for root, dirs, files in os.walk(directory):
        # Skip venv, node_modules
        dirs[:] = [d for d in dirs if d not in ['venv', 'node_modules', '__pycache__']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Replace imports
                new_content = content.replace('from src.', 'from backend.')
                new_content = new_content.replace('import src.', 'import backend.')
                
                if new_content != content:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Updated: {filepath}")

if __name__ == "__main__":
    update_imports("backend")
    print("✅ Import paths updated!")
```

Run it:
```powershell
cd C:\team-data-platform\apps\fashion-assistant
python update_imports.py
```

---

### **STEP 5: Create Docker Configuration**

Create `backend/Dockerfile`:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/
COPY data/ ./data/

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Run backend
CMD ["uvicorn", "backend.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `frontend/Dockerfile`:
```dockerfile
FROM node:18-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy source
COPY . .

# Build
RUN npm run build

# Production image
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

---

### **STEP 6: Create Team docker-compose.yml**

Create `infrastructure/docker/docker-compose.yml`:

```yaml
version: '3.8'

services:
  # Your Fashion Assistant Backend
  fashion-assistant-backend:
    build:
      context: ../../apps/fashion-assistant
      dockerfile: backend/Dockerfile
    container_name: fashion-assistant-backend
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DATABASE_URL=${DATABASE_URL}
    volumes:
      - ../../apps/fashion-assistant/backend:/app/backend
      - ../../apps/fashion-assistant/data:/app/data
    networks:
      - data-platform-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Your Fashion Assistant Frontend
  fashion-assistant-frontend:
    build:
      context: ../../apps/fashion-assistant/frontend
      dockerfile: Dockerfile
    container_name: fashion-assistant-frontend
    ports:
      - "3000:80"
    depends_on:
      - fashion-assistant-backend
    networks:
      - data-platform-network

  # Data Mesh Service (Team Member 1)
  data-mesh:
    build:
      context: ../../services/data-mesh
      dockerfile: Dockerfile
    container_name: data-mesh
    ports:
      - "8001:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
    networks:
      - data-platform-network
    # Uncomment when service is ready
    # healthcheck:
    #   test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    #   interval: 30s

  # Data Fabric Service (Team Member 2)
  data-fabric:
    build:
      context: ../../services/data-fabric
      dockerfile: Dockerfile
    container_name: data-fabric
    ports:
      - "8002:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
    networks:
      - data-platform-network

  # Data Architecture Service (Team Member 3)
  data-architecture:
    build:
      context: ../../services/data-architecture
      dockerfile: Dockerfile
    container_name: data-architecture
    ports:
      - "8003:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
    networks:
      - data-platform-network

  # Nginx Reverse Proxy (Optional - for routing)
  nginx-gateway:
    image: nginx:alpine
    container_name: nginx-gateway
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ../nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - fashion-assistant-backend
      - data-mesh
      - data-fabric
      - data-architecture
    networks:
      - data-platform-network

  # PostgreSQL Database (Shared)
  postgres:
    image: postgres:15-alpine
    container_name: postgres-db
    environment:
      POSTGRES_USER: ${DB_USER:-dataplatform}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-changeme}
      POSTGRES_DB: ${DB_NAME:-dataplatform}
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - data-platform-network

  # Redis Cache (Shared)
  redis:
    image: redis:7-alpine
    container_name: redis-cache
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    networks:
      - data-platform-network

networks:
  data-platform-network:
    driver: bridge

volumes:
  postgres-data:
  redis-data:
```

---

### **STEP 7: Create .gitignore for Team Repo**

Create `C:\team-data-platform\.gitignore`:
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# Node
node_modules/
dist/
build/
npm-debug.log*

# Environment
.env
.env.local
*.env

# IDEs
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Data
*.csv
*.npy
*.pkl
data/raw/*
data/processed/*
!data/raw/.gitkeep
!data/processed/.gitkeep

# Logs
logs/
*.log

# Docker
*.pid
*.sock

# Cache
.pytest_cache/
.mypy_cache/
```

---

### **STEP 8: Create README.md for Team**

Create `C:\team-data-platform\README.md`:

```markdown
# Data Platform - Team Project

Multi-component data platform with user-facing applications and backend data services.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│              User Applications Layer                 │
│  ┌─────────────────────────────────────────┐       │
│  │    Fashion Assistant (Chatbot + UI)     │       │
│  └─────────────────┬───────────────────────┘       │
│                    │                                │
└────────────────────┼────────────────────────────────┘
                     │
┌────────────────────┼────────────────────────────────┐
│              Services Layer (APIs)                  │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐    │
│  │   Data   │  │   Data    │  │    Data      │    │
│  │   Mesh   │  │  Fabric   │  │ Architecture │    │
│  └──────────┘  └───────────┘  └──────────────┘    │
└────────────────────┼────────────────────────────────┘
                     │
┌────────────────────┼────────────────────────────────┐
│              Data Layer                             │
│      PostgreSQL  │  Redis  │  Data Storage         │
└─────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### Setup
```bash
# Clone repository
git clone <repo-url>
cd team-data-platform

# Copy environment file
cp .env.example .env
# Edit .env with your credentials

# Start all services
cd infrastructure/docker
docker-compose up -d

# Access services
# Fashion Assistant: http://localhost:3000
# Data Mesh API: http://localhost:8001
# Data Fabric API: http://localhost:8002
# Data Architecture API: http://localhost:8003
```

## 📁 Repository Structure

- **apps/fashion-assistant** - User-facing chatbot and recommendation engine
- **services/data-mesh** - Data mesh implementation
- **services/data-fabric** - Data fabric layer
- **services/data-architecture** - Data architecture services
- **shared/** - Shared utilities and configurations
- **infrastructure/** - Docker, Nginx, deployment configs
- **docs/** - Documentation

## 👥 Team Components

| Component | Owner | Port | Status |
|-----------|-------|------|--------|
| Fashion Assistant | You | 8000 | ✅ Active |
| Data Mesh | Team Member 1 | 8001 | 🚧 In Progress |
| Data Fabric | Team Member 2 | 8002 | 🚧 In Progress |
| Data Architecture | Team Member 3 | 8003 | 🚧 In Progress |

## 🔧 Development

See [docs/setup-guide.md](docs/setup-guide.md) for detailed setup instructions.

## 📄 License

[Your License]
```

---

### **STEP 9: Sync Strategy (Critical for Parallel Development)**

Create `C:\sync-to-team.ps1` (PowerShell script to sync changes):

```powershell
# Sync script: Copy changes from TEST_RP to team repo
# Run this whenever you want to sync your solo work to team repo

$SOURCE = "C:\TEST_RP"
$DEST = "C:\team-data-platform\apps\fashion-assistant"

Write-Host "🔄 Syncing from TEST_RP to team repo..." -ForegroundColor Cyan

# Sync backend
Write-Host "  📦 Syncing backend..." -ForegroundColor Yellow
robocopy "$SOURCE\src" "$DEST\backend" /E /XD __pycache__ .pytest_cache /XF *.pyc /MIR

# Sync frontend
Write-Host "  🎨 Syncing frontend..." -ForegroundColor Yellow
robocopy "$SOURCE\frontend" "$DEST\frontend" /E /XD node_modules dist /MIR

# Sync data (be careful with large files)
Write-Host "  📊 Syncing data..." -ForegroundColor Yellow
robocopy "$SOURCE\data" "$DEST\data" /E /XF *.npy *.pkl

# Sync requirements
Write-Host "  📋 Syncing requirements..." -ForegroundColor Yellow
Copy-Item "$SOURCE\requirements.txt" "$DEST\backend\requirements.txt" -Force

# Sync docs
Write-Host "  📖 Syncing docs..." -ForegroundColor Yellow
Copy-Item "$SOURCE\PROJECT_SUMMARY.md" "$DEST\README.md" -Force

Write-Host "✅ Sync complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. cd C:\team-data-platform" -ForegroundColor White
Write-Host "  2. git status" -ForegroundColor White
Write-Host "  3. git add ." -ForegroundColor White
Write-Host "  4. git commit -m 'Sync fashion-assistant updates'" -ForegroundColor White
Write-Host "  5. git push" -ForegroundColor White
```

Make it executable:
```powershell
cd C:\
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## 🔄 Development Workflow

### **Daily Workflow:**

```powershell
# Morning: Pull team changes
cd C:\team-data-platform
git pull origin main

# Work on your component
cd C:\TEST_RP
# ... make changes, test, commit locally ...

# Afternoon: Sync your changes to team repo
cd C:\
.\sync-to-team.ps1

# Review and push
cd C:\team-data-platform
git status
git add apps/fashion-assistant
git commit -m "feat: add new personalization feature"
git push origin main
```

### **Testing Integration:**

```powershell
# Test your component with team services
cd C:\team-data-platform\infrastructure\docker
docker-compose up fashion-assistant-backend data-mesh

# Test only your service
docker-compose up fashion-assistant-backend fashion-assistant-frontend
```

---

## 🛡️ Avoiding Integration Issues

### **1. API Contracts (Critical)**

Create `docs/api-contracts.md`:
```markdown
# API Contracts

## Fashion Assistant ← Data Mesh
- **Endpoint:** GET /api/products/recommendations
- **Request:** `{"user_id": int, "category": str}`
- **Response:** `{"products": [...], "metadata": {...}}`

## Fashion Assistant ← Data Fabric
- **Endpoint:** GET /api/user/preferences
- **Request:** `{"user_id": int}`
- **Response:** `{"preferences": {...}}`
```

**Rule:** Never break these contracts without team discussion.

### **2. Environment Variables (Shared)**

Create `.env.example`:
```env
# Shared Database
DATABASE_URL=postgresql://user:pass@postgres:5432/dataplatform

# Shared Redis
REDIS_URL=redis://redis:6379/0

# Service-Specific
OPENAI_API_KEY=your_key_here
FASHION_ASSISTANT_PORT=8000
DATA_MESH_PORT=8001
DATA_FABRIC_PORT=8002
DATA_ARCH_PORT=8003
```

### **3. Use Feature Branches**

```powershell
# Create feature branch for risky changes
cd C:\team-data-platform
git checkout -b feature/new-recommendation-algo

# Make changes, test, commit
git add .
git commit -m "feat: new recommendation algorithm"

# Push for review
git push origin feature/new-recommendation-algo

# Create Pull Request on GitHub/GitLab
# After approval, merge to main
```

### **4. Docker Health Checks**

Add to each service to detect failures early:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### **5. Integration Tests**

Create `tests/e2e/test_integration.py`:
```python
import requests

def test_fashion_assistant_to_data_mesh():
    # Test that your service can call data mesh
    response = requests.get("http://localhost:8001/api/products")
    assert response.status_code == 200
    
def test_full_user_flow():
    # Test complete user journey
    # 1. User queries fashion assistant
    query_response = requests.post("http://localhost:8000/api/answer", 
                                    json={"text": "blue pants"})
    assert query_response.status_code == 200
    
    # 2. Check data mesh was called (via logs or monitoring)
    # ...
```

---

## ✅ Final Checklist

Before pushing to team repo:

- [ ] All import paths updated (`src.` → `backend.`)
- [ ] `.env.example` created with all required variables
- [ ] README.md explains your component
- [ ] Dockerfile works (`docker build -t test .`)
- [ ] Component runs standalone (`docker-compose up fashion-assistant-backend`)
- [ ] API endpoints documented in `docs/api-contracts.md`
- [ ] Health check endpoint implemented (`/api/health`)
- [ ] Sensitive data (.env, API keys) in .gitignore
- [ ] Original TEST_RP repo still works independently

---

## 🎯 Summary

**YES, copying your folder will work!** 

Follow this approach:
1. ✅ Keep original TEST_RP for solo development
2. ✅ Copy to team-data-platform for integration
3. ✅ Use sync script to push changes from solo → team
4. ✅ Use feature branches for experimental changes
5. ✅ Define API contracts before coding
6. ✅ Test integration early and often

**Your component will be isolated in `apps/fashion-assistant/` so team members can work independently without breaking your code.**

Good luck with the integration! 🚀
