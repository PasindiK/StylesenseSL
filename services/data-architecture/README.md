# Data Architecture Service

Data governance and quality assurance service for the team data platform.

## 📋 Overview

This service handles:
- Data quality monitoring
- Schema management and versioning
- Data lineage tracking
- Governance policies and compliance

## 📁 Structure

```
data-architecture/
├── src/
│   ├── main.py              # Service entry point
│   ├── quality/             # Quality checks
│   ├── schema/              # Schema management
│   ├── lineage/             # Lineage tracking
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

# Service runs on port 8003
curl http://localhost:8003/health
```

### Docker

```bash
# Build image
docker build -t data-architecture:latest .

# Run container
docker run -p 8003:8003 data-architecture:latest
```

## 🔌 API Endpoints

### Health Check
```bash
GET /api/health
```

### Validate Data Quality
```bash
POST /api/validate
Content-Type: application/json

{
  "table": "products",
  "checks": [
    {"type": "null_check", "column": "product_id"},
    {"type": "range_check", "column": "price", "min": 0, "max": 100000}
  ]
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
- **Data Mesh:** `http://data-mesh:8001`
- **Data Fabric:** `http://data-fabric:8002`

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
