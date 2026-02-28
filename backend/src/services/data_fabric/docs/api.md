# API Documentation

## Overview

The Data Fabric API provides RESTful endpoints for all major operations including ingestion, preprocessing, validation, metadata management, and ML operations.

## Base URL

```
http://localhost:8000/api
```

## Health & Status Endpoints

### Health Check
```
GET /health/ping
```

Response:
```json
{
  "status": "healthy",
  "message": "Data Fabric API is running"
}
```

### API Status
```
GET /health/status
```

Response:
```json
{
  "status": "running",
  "version": "1.0.0",
  "service": "Data Fabric API"
}
```

## Ingestion Endpoints

### Extract Data
```
POST /ingestion/extract

Body:
{
  "source_type": "csv",
  "source_location": "/path/to/file.csv"
}
```

Response:
```json
{
  "status": "success",
  "source_type": "csv",
  "rows_extracted": 1000,
  "message": "Extraction completed"
}
```

### Upload File
```
POST /ingestion/upload

Body: multipart/form-data with file
```

### List Sources
```
GET /ingestion/sources
```

Response:
```json
{
  "sources": [
    {
      "id": "source1",
      "name": "CSV Source",
      "type": "csv"
    }
  ]
}
```

## Preprocessing Endpoints

### Transform Data
```
POST /preprocessing/transform

Body:
{
  "dataset_id": "dataset1",
  "transformations": [
    {
      "type": "column_rename",
      "parameters": {"old_name": "col1", "new_name": "column1"}
    }
  ]
}
```

### Clean Data
```
POST /preprocessing/clean

Body:
{
  "dataset_id": "dataset1",
  "cleaning_config": {
    "strategy": "drop",
    "remove_duplicates": true
  }
}
```

### Normalize Data
```
POST /preprocessing/normalize

Body:
{
  "dataset_id": "dataset1",
  "method": "standard"  // standard, minmax, robust, log
}
```

## Validation Endpoints

### Validate Dataset
```
POST /validation/validate

Body:
{
  "dataset_id": "dataset1",
  "rules": ["schema_check", "completeness", "uniqueness"]
}
```

## Metadata Endpoints

### List Assets
```
GET /metadata/assets?asset_type=table&access_level=internal
```

Response:
```json
{
  "assets": [
    {
      "asset_id": "asset1",
      "name": "Customer Data",
      "owner": "Data Team",
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "total": 1
}
```

### Get Asset
```
GET /metadata/assets/{asset_id}
```

### Register Asset
```
POST /metadata/assets

Body:
{
  "name": "New Dataset",
  "description": "Dataset description",
  "owner": "data_team",
  "asset_type": "table",
  "tags": ["raw", "customer"]
}
```

### Get Lineage
```
GET /metadata/lineage/{asset_id}
```

Response:
```json
{
  "asset_id": "asset1",
  "upstream": ["source1", "source2"],
  "downstream": ["report1", "model1"],
  "operations": ["transform1", "aggregate1"]
}
```

## ML Endpoints

### Train Model
```
POST /ml/train

Body:
{
  "model_type": "random_forest",
  "dataset_id": "dataset1",
  "hyperparameters": {
    "n_estimators": 100,
    "max_depth": 10
  }
}
```

Response:
```json
{
  "status": "success",
  "model_id": "model_123",
  "model_type": "random_forest",
  "accuracy": 0.95,
  "message": "Model training completed"
}
```

### Make Predictions
```
POST /ml/predict

Body:
{
  "model_id": "model_123",
  "data": {
    "feature_1": 1.5,
    "feature_2": 2.0,
    "feature_3": 0.5
  }
}
```

Response:
```json
{
  "status": "success",
  "model_id": "model_123",
  "predictions": [0, 1],
  "confidence": [0.92, 0.88]
}
```

### List Models
```
GET /ml/models
```

Response:
```json
{
  "models": [
    {
      "model_id": "model_123",
      "model_type": "classification",
      "accuracy": 0.95,
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "total": 1
}
```

### Get Model
```
GET /ml/models/{model_id}
```

## Error Responses

### 400 Bad Request
```json
{
  "error": "Invalid request parameters"
}
```

### 401 Unauthorized
```json
{
  "error": "Missing or invalid authorization token"
}
```

### 404 Not Found
```json
{
  "error": "Resource not found"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error"
}
```

## Authentication

Include JWT token in request headers:
```
Authorization: Bearer your_jwt_token_here
```

## Rate Limiting

- 1000 requests per hour per API key
- Exceeded limit returns 429 Too Many Requests

## SDK Usage

### Python Example
```python
import requests

API_BASE = "http://localhost:8000/api"
headers = {"Authorization": "Bearer token"}

# Extract data
response = requests.post(
    f"{API_BASE}/ingestion/extract",
    json={"source_type": "csv", "source_location": "data.csv"},
    headers=headers
)

# Train model
response = requests.post(
    f"{API_BASE}/ml/train",
    json={
        "model_type": "random_forest",
        "dataset_id": "dataset1"
    },
    headers=headers
)

# Make predictions
response = requests.post(
    f"{API_BASE}/ml/predict",
    json={
        "model_id": "model_123",
        "data": {"feature_1": 1.5, "feature_2": 2.0}
    },
    headers=headers
)
```

## Webhook Notifications

Coming soon: Configure webhooks for workflow completion and model training notifications.
