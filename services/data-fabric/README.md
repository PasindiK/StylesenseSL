# Data Fabric Service

Data transformation and aggregation service for the team data platform.

## 📋 Overview

This service handles:
- Data transformation and enrichment
- Data aggregation from multiple sources
- Joining and merging datasets
- Feature engineering

## 📁 Structure

```
data-fabric/
├── src/
│   ├── main.py              # Service entry point
│   ├── transformers/        # Transformation logic
│   ├── aggregators/         # Aggregation logic
│   ├── features/            # Feature engineering
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

# Service runs on port 8002
curl http://localhost:8002/health
```

### Docker

```bash
# Build image
docker build -t data-fabric:latest .

# Run container
docker run -p 8002:8002 data-fabric:latest
```

## 🔌 API Endpoints

### Health Check
```bash
GET /api/health
```

### Transform Data
```bash
POST /api/transform
Content-Type: application/json

{
  "source_table": "raw_data",
  "transformations": [
    {"type": "normalize", "field": "price"},
    {"type": "encode", "field": "category"}
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
