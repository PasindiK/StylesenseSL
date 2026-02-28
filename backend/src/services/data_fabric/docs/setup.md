# Setup and Development Guide

## Prerequisites

- Python 3.9 or higher
- PostgreSQL 12+ (for database operations)
- pip and virtualenv

## Local Development Setup

### 1. Environment Setup

```bash
# Clone repository
git clone <repository-url>
cd data-fabric

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip
```

### 2. Install Dependencies

```bash
# Install from requirements.txt
pip install -r requirements.txt

# Install in development mode with testing dependencies
pip install -e ".[dev]"
```

### 3. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env  # or use your preferred editor
```

Key environment variables to configure:
```
DATABASE_URL=postgresql://user:password@localhost:5432/data_fabric
API_PORT=8000
LOG_LEVEL=DEBUG
ENVIRONMENT=development
```

### 4. Database Setup

```bash
# Create PostgreSQL database
createdb data_fabric

# Create tables (if using SQLAlchemy models)
python -c "from src.ingestion import *; Base.metadata.create_all(engine)"
```

### 5. Verify Installation

```bash
# Run health check
python -c "from src.ingestion import CSVExtractor; print('Import successful')"

# Run tests
pytest --version
```

## Running the Application

### Start API Server

```bash
# Development mode with auto-reload
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Access API documentation at:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

### Run Automation Scripts

```bash
# Data ingestion
python scripts/data_ingestion.py \
  --source csv \
  --path data/sample.csv \
  --log-level DEBUG

# Validation
python scripts/validation_runner.py \
  --dataset data/processed.csv \
  --config validation_config.json

# Metadata sync
python scripts/metadata_sync.py \
  --catalog-path metadata/catalog.json

# ML training
python scripts/ml_training.py \
  --dataset data/train.csv \
  --model random_forest
```

## Testing

### Run All Tests

```bash
# Standard test run
pytest

# With coverage report
pytest --cov=src --cov-report=html

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Run Specific Tests

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Single test file
pytest tests/unit/test_ingestion.py

# Single test function
pytest tests/unit/test_ingestion.py::TestCSVExtractor::test_extract_csv
```

### Test Coverage Goals

- Overall: >80% coverage
- Core modules (ingestion, validation, preprocessing): >90% coverage
- API routes: >75% coverage

## Code Quality

### Code Formatting

```bash
# Format code with Black
black src/ tests/

# Check formatting
black --check src/ tests/
```

### Linting

```bash
# Check code with flake8
flake8 src/ tests/

# Configuration in .flake8
# - max line length: 88
# - ignore: E203, W503
```

### Type Checking

```bash
# Run mypy for static type checking
mypy src/

# Generate report
mypy src/ --html report/
```

### Code Standards

- Follow PEP 8 style guide
- Use type hints for all functions
- Maximum line length: 88 characters
- Use docstrings for all modules and classes

## Docker Development

### Build Image

```bash
docker build -t data-fabric:latest .
```

### Run Container

```bash
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql://user:password@db:5432/data_fabric \
  data-fabric:latest
```

### Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Debugging

### Enable Debug Logging

```bash
# Set in .env
LOG_LEVEL=DEBUG

# Or via command line
python scripts/data_ingestion.py --source csv --path data.csv --log-level DEBUG
```

### Using Python Debugger

```python
import pdb; pdb.set_trace()  # Breakpoint
```

### IDE Debugging

**VS Code** (.vscode/launch.json):
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["src.api.main:app", "--reload"],
      "jinja": true
    }
  ]
}
```

## Common Issues

### Issue: ModuleNotFoundError
```bash
# Solution: Add project root to Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Issue: Database connection error
```bash
# Check PostgreSQL is running
psql -U postgres -d data_fabric -c "SELECT 1"

# Update DATABASE_URL in .env
```

### Issue: Port 8000 already in use
```bash
# Use different port
uvicorn src.api.main:app --port 8888

# Or kill process using port
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9
```

## Documentation Generation

### Generate API Documentation

```bash
# Already available at /api/docs and /api/redoc
# No additional setup needed
```

### Generate Code Documentation

```bash
# Using pdoc
pip install pdoc3
pdoc3 -o docs/code src/

# Using Sphinx
pip install sphinx
sphinx-quickstart docs
cd docs && make html
```

## Performance Profiling

### Profile CPU Usage

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Your code here

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative').print_stats(10)
```

### Memory Profiling

```bash
pip install memory-profiler
python -m memory_profiler script.py
```

## Continuous Integration

### GitHub Actions

Create `.github/workflows/test.yml`:
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: pytest
      - run: black --check .
      - run: flake8 .
```

## Production Deployment

### Pre-deployment Checklist

- [ ] All tests pass
- [ ] Code coverage >80%
- [ ] No linting errors
- [ ] Type hints complete
- [ ] Documentation updated
- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] Secrets securely managed

### Deployment Steps

```bash
# 1. Build production image
docker build -t data-fabric:v1.0.0 .

# 2. Push to registry
docker push your-registry/data-fabric:v1.0.0

# 3. Deploy to Kubernetes
kubectl apply -f k8s/

# 4. Verify deployment
kubectl rollout status deployment/data-fabric
```

## Getting Help

- Check documentation in `/docs`
- Review examples in `/tests`
- Search existing GitHub issues
- Create new issue with details and logs
- Open discussion for questions
