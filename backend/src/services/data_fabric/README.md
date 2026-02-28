# Data Fabric - Enterprise Data Management Architecture

A modular, production-ready Python project for building scalable data fabric systems.

## Overview

Data Fabric is a comprehensive architecture for managing data flows across enterprise systems. It provides:

- **Ingestion Layer**: Extract data from multiple sources (CSV, databases, APIs, S3)
- **Preprocessing Layer**: Clean, transform, and normalize data
- **Validation Layer**: Ensure data quality through comprehensive checks
- **Metadata Catalog**: Track data lineage and manage metadata
- **Integration Layer**: Orchestrate workflows and manage pipelines
- **ML Engine**: Train, serve, and manage machine learning models
- **FastAPI**: RESTful API for easy integration
- **Automation Scripts**: Command-line tools for batch processing
- **Comprehensive Logging**: Structured logging across all layers
- **Production Testing**: Unit and integration tests

## Project Structure

```
data-fabric/
├── src/                          # Main source code
│   ├── ingestion/               # Data ingestion layer
│   │   ├── sources.py          # Data source definitions
│   │   ├── connectors.py       # Connection management
│   │   └── extractors.py       # Data extraction
│   ├── preprocessing/           # Data preprocessing
│   │   ├── transformers.py     # Data transformations
│   │   ├── cleaners.py         # Data cleaning
│   │   └── normalizers.py      # Data normalization
│   ├── validation/             # Data quality validation
│   │   ├── validators.py       # Schema and value validation
│   │   ├── quality_checks.py   # Quality metrics
│   │   └── rules.py            # Validation rules engine
│   ├── metadata/               # Metadata management
│   │   ├── catalog.py          # Data asset catalog
│   │   ├── lineage.py          # Data lineage tracking
│   │   └── registry.py         # Metadata registry
│   ├── integration/            # Workflow orchestration
│   │   ├── orchestrator.py     # Workflow orchestrator
│   │   └── workflows.py        # Workflow definitions
│   ├── ml_engine/              # Machine learning
│   │   ├── models.py           # Model management
│   │   ├── training.py         # Model training
│   │   └── prediction.py       # Model prediction
│   └── api/                    # REST API
│       ├── main.py             # FastAPI app
│       ├── routes/             # API endpoints
│       ├── schemas/            # Pydantic models
│       └── middleware/         # API middleware
├── configs/                    # Configuration management
├── logs/                       # Logging configuration
├── scripts/                    # Automation scripts
│   ├── data_ingestion.py      # Data ingestion script
│   ├── validation_runner.py   # Validation automation
│   ├── metadata_sync.py       # Metadata synchronization
│   └── ml_training.py         # ML training automation
├── tests/                      # Test suite
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   └── fixtures/              # Test fixtures
├── docs/                      # Documentation
├── setup.py                   # Package setup
├── requirements.txt           # Dependencies
├── .env.example              # Environment template
└── README.md                 # This file
```

## Installation

### 1. Clone the repository
```bash
git clone <repository-url>
cd data-fabric
```

### 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Setup environment
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Quick Start

### Using the Python API

```python
from src.ingestion import CSVExtractor
from src.preprocessing import MissingValueHandler, StandardScaler
from src.validation import SchemaValidator

# 1. Ingest data
extractor = CSVExtractor()
df = extractor.extract("data/raw_data.csv")

# 2. Clean data
cleaner = MissingValueHandler(strategy="drop")
df_clean = cleaner.clean(df)

# 3. Normalize data
scaler = StandardScaler()
df_normalized = scaler.fit_transform(df_clean)

# 4. Validate data
schema = {"age": "int", "salary": "float"}
validator = SchemaValidator(schema)
result = validator.validate(df_normalized)
```

### Running the API

```bash
# Start the FastAPI server
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# API will be available at http://localhost:8000/api/docs
```

### Running Automation Scripts

```bash
# Data ingestion
python scripts/data_ingestion.py --source csv --path data/raw.csv

# Data validation
python scripts/validation_runner.py --dataset data/processed.csv --config validation_config.json

# Metadata synchronization
python scripts/metadata_sync.py --catalog-path metadata/catalog.json

# ML model training
python scripts/ml_training.py --dataset data/train.csv --model random_forest
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Run specific test module
pytest tests/unit/test_ingestion.py

# Run integration tests
pytest tests/integration/

# Run with verbose output
pytest -v
```

## Core Components

### Ingestion Layer
- **CSVExtractor**: Extract data from CSV files
- **DatabaseExtractor**: Query databases (PostgreSQL, MySQL, etc.)
- **APIExtractor**: Fetch data from REST APIs
- **S3Connector**: Connect to AWS S3 buckets
- **SourceRegistry**: Manage data sources

### Preprocessing Layer
- **DataClean**: Handle missing values, remove duplicates
- **OutlierHandler**: Detect and handle outliers
- **DataTransformer**: Type conversion, feature engineering
- **StandardScaler**: Standardize numeric features
- **MinMaxScaler**: Scale to fixed range (0, 1)

### Validation Layer
- **SchemaValidator**: Validate data schema
- **RangeValidator**: Validate value ranges
- **RuleEngine**: Execute custom validation rules
- **QualityChecker**: Measure data quality metrics
- **PatternValidator**: Validate data patterns with regex

### Metadata Layer
- **MetadataCatalog**: Discover and manage data assets
- **LineageTracker**: Track data transformations
- **MetadataRegistry**: Version and manage metadata
- **DataAsset**: Model for data assets in the catalog

### Integration Layer
- **WorkflowOrchestrator**: Orchestrate complex workflows
- **Workflow**: Define multi-step data pipelines
- **WorkflowExecutor**: Execute workflows with error handling

### ML Engine
- **ModelTrainer**: Train scikit-learn and TensorFlow models
- **ModelRegistry**: Manage model versions
- **ModelPredictor**: Make predictions with trained models
- **HyperparameterTuner**: Optimize model hyperparameters

### API Layer
- RESTful endpoints for all core operations
- Pydantic models for request/response validation
- Authentication middleware
- CORS support
- Comprehensive API documentation

## Configuration

All configuration is managed through environment variables. See `.env.example` for available options:

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/data_fabric

# API
API_HOST=0.0.0.0
API_PORT=8000

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

# ML
ML_MODEL_PATH=./models
ML_BATCH_SIZE=32

# Storage
STORAGE_BUCKET=data-fabric
STORAGE_REGION=us-east-1
```

## Logging

Logging is configured in `logs/config.yaml`. Features include:

- Rotating file handlers to prevent log files from growing too large
- Separate error log file
- Module-specific log levels
- Structured logging with timestamps and context

## Development

### Code Quality Tools

```bash
# Format code with Black
black src/ tests/

# Check style with flake8
flake8 src/ tests/

# Type checking with mypy
mypy src/
```

### Running the Development Server

```bash
# With auto-reload
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## Production Deployment

### Docker

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Kubernetes

Use the provided docker image with Kubernetes manifests for orchestration.

## API Documentation

Once running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

## Contributing

1. Create a feature branch
2. Make your changes
3. Add tests for new functionality
4. Run the test suite
5. Submit a pull request

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions, please open an issue on GitHub.
