# Data Mesh Service

Data ingestion and validation service for the team data platform.

## 📋 Overview

This service handles:
- Data ingestion from various sources
- Data validation and quality checks
- Schema validation
- Data pipeline orchestration

## 📁 Structure

```
data-mesh/
├── src/
│   ├── main.py              # Service entry point
│   ├── models/              # Data models & schemas
│   ├── pipelines/           # Ingestion pipelines
│   ├── validators/          # Validation logic
│   └── __init__.py
├── requirements.txt         # Python dependencies
├── Dockerfile               # Container configuration
├── .env.example             # Environment variables
└── README.md               # This file
```

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Docker

### Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
```

### Run Locally

```bash
# Start service
python -m src.main

# Service runs on port 8001
curl http://localhost:8001/health
```

### Docker

```bash
# Build image
docker build -t data-mesh:latest .

# Run container
docker run -p 8001:8001 data-mesh:latest
```

## 🔌 API Endpoints

### Health Check
```bash
GET /api/health
```

### Ingest Data
```bash
POST /api/ingest
Content-Type: application/json

{
  "source": "s3://bucket/data",
  "format": "csv",
  "destination": "staging_db"
}
```

## 📝 Adding Your Code

1. Place your main logic in `src/main.py`
2. Create modules in `src/` as needed
3. Add dependencies to `requirements.txt`
4. Update this README with your specific functionality

## 🔗 Integration with Team

This service integrates with:
- **Fashion Assistant:** `http://fashion-assistant-backend:8000`
- **Data Fabric:** `http://data-fabric:8002`
- **Data Architecture:** `http://data-architecture:8003`

## ✅ Checklist

- [ ] Add your code to `src/`
- [ ] Update `requirements.txt`
- [ ] Customize `main.py`
- [ ] Build and test Docker image
- [ ] Push to team repository
- [ ] Add to docker-compose.yml

---

**Team Member:** [Your Name]
**Last Updated:** February 28, 2026
