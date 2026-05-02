# Service-Level RBAC Testing Guide

This guide explains how to test the role-based access control system for the three services: Data Fabric, Data Mesh, and Agentic AI.

## Service Principals

Three service principals are pre-configured:

| Service | Principal ID | Container | Allowed Layers | Operations |
|---------|-------------|-----------|----------------|------------|
| **Data Fabric** | `sp_data_fabric_001` | `data-fabric` | bronze, silver, gold | read, write, execute, transform |
| **Data Mesh** | `sp_data_mesh_001` | `data-mesh` | silver, gold | read, write, publish |
| **Agentic AI** | `sp_agentic_ai_001` | `agentic-ai` | gold | read, write, inference, train |

## Endpoint: Get RBAC Configuration

Returns the full RBAC configuration with all service principals and their permissions.

```bash
curl -X GET http://localhost:8000/api/governance/service-rbac
```

**Response:**
```json
{
  "generated_at": "2024-01-15T10:30:45Z",
  "service_principals": [
    {
      "service_name": "data_fabric",
      "principal_id": "sp_data_fabric_001",
      "container": "data-fabric",
      "allowed_operations": ["read", "write", "execute", "transform"],
      "allowed_layers": ["bronze", "silver", "gold"],
      "data_categories": ["customer", "product", "transaction", "inventory", "ml_features"],
      "created_at": "2024-01-01T00:00:00Z"
    },
    {
      "service_name": "data_mesh",
      "principal_id": "sp_data_mesh_001",
      "container": "data-mesh",
      "allowed_operations": ["read", "write", "publish"],
      "allowed_layers": ["silver", "gold"],
      "data_categories": ["product", "customer", "domain_views", "business_metrics"],
      "created_at": "2024-01-01T00:00:00Z"
    },
    {
      "service_name": "agentic_ai",
      "principal_id": "sp_agentic_ai_001",
      "container": "agentic-ai",
      "allowed_operations": ["read", "write", "inference", "train"],
      "allowed_layers": ["gold"],
      "data_categories": ["ml_features", "embeddings", "customer", "product", "personalization"],
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total_services": 3,
  "exported_at": "2024-01-15T10:30:45Z"
}
```

## Endpoint: Check Service Access

Validate if a service has access to perform a specific operation on a data layer.

### Test 1: Data Fabric reading from bronze layer (ALLOWED)

```bash
curl -X POST "http://localhost:8000/api/governance/service-access-check?service_name=data_fabric&operation=read&layer=bronze&data_category=customer"
```

**Expected Response [ALLOWED]:**
```json
{
  "generated_at": "2024-01-15T10:35:20Z",
  "service_name": "data_fabric",
  "operation": "read",
  "layer": "bronze",
  "data_category": "customer",
  "access_granted": true,
  "reason": "data_fabric has read operation on bronze layer for customer category"
}
```

### Test 2: Data Mesh reading from bronze layer (DENIED)

```bash
curl -X POST "http://localhost:8000/api/governance/service-access-check?service_name=data_mesh&operation=read&layer=bronze"
```

**Expected Response [DENIED]:**
```json
{
  "generated_at": "2024-01-15T10:35:25Z",
  "service_name": "data_mesh",
  "operation": "read",
  "layer": "bronze",
  "data_category": "",
  "access_granted": false,
  "reason": "data_mesh is not allowed to access bronze layer"
}
```

### Test 3: Agentic AI training on gold layer (ALLOWED)

```bash
curl -X POST "http://localhost:8000/api/governance/service-access-check?service_name=agentic_ai&operation=train&layer=gold&data_category=ml_features"
```

**Expected Response [ALLOWED]:**
```json
{
  "generated_at": "2024-01-15T10:35:30Z",
  "service_name": "agentic_ai",
  "operation": "train",
  "layer": "gold",
  "data_category": "ml_features",
  "access_granted": true,
  "reason": "agentic_ai has train operation on gold layer for ml_features category"
}
```

### Test 4: Agentic AI transforming data (DENIED - not allowed operation)

```bash
curl -X POST "http://localhost:8000/api/governance/service-access-check?service_name=agentic_ai&operation=transform&layer=gold"
```

**Expected Response [DENIED]:**
```json
{
  "generated_at": "2024-01-15T10:35:35Z",
  "service_name": "agentic_ai",
  "operation": "transform",
  "layer": "gold",
  "data_category": "",
  "access_granted": false,
  "reason": "agentic_ai does not have transform operation permission"
}
```

## Endpoint: Service RBAC Audit Log

View access attempts and decisions for compliance tracking.

### Get recent audit log

```bash
curl -X GET "http://localhost:8000/api/governance/service-rbac/audit-log?limit=50"
```

**Response:**
```json
{
  "generated_at": "2024-01-15T10:40:00Z",
  "service_filter": null,
  "total_entries": 4,
  "entries": [
    {
      "timestamp": "2024-01-15T10:35:20Z",
      "service_name": "data_fabric",
      "operation": "read",
      "layer": "bronze",
      "data_category": "customer",
      "access_granted": true,
      "reason": "data_fabric has read operation on bronze layer for customer category"
    },
    {
      "timestamp": "2024-01-15T10:35:25Z",
      "service_name": "data_mesh",
      "operation": "read",
      "layer": "bronze",
      "data_category": "",
      "access_granted": false,
      "reason": "data_mesh is not allowed to access bronze layer"
    },
    {
      "timestamp": "2024-01-15T10:35:30Z",
      "service_name": "agentic_ai",
      "operation": "train",
      "layer": "gold",
      "data_category": "ml_features",
      "access_granted": true,
      "reason": "agentic_ai has train operation on gold layer for ml_features category"
    },
    {
      "timestamp": "2024-01-15T10:35:35Z",
      "service_name": "agentic_ai",
      "operation": "transform",
      "layer": "gold",
      "data_category": "",
      "access_granted": false,
      "reason": "agentic_ai does not have transform operation permission"
    }
  ]
}
```

### Filter by service

```bash
curl -X GET "http://localhost:8000/api/governance/service-rbac/audit-log?service_name=data_fabric&limit=100"
```

**Response:**
```json
{
  "generated_at": "2024-01-15T10:40:05Z",
  "service_filter": "data_fabric",
  "total_entries": 1,
  "entries": [
    {
      "timestamp": "2024-01-15T10:35:20Z",
      "service_name": "data_fabric",
      "operation": "read",
      "layer": "bronze",
      "data_category": "customer",
      "access_granted": true,
      "reason": "data_fabric has read operation on bronze layer for customer category"
    }
  ]
}
```

## Integration with Existing Endpoints

The RBAC system integrates with existing medallion data access endpoints:

- `/api/medallion/{layer}/files` - List files in a medallion layer
- `/api/medallion/{layer}/download` - Download files from a layer
- `/api/medallion/{layer}/upload` - Upload files to a layer

Future enhancement: Add `@require_rbac()` decorator to these endpoints to enforce RBAC checks before data operations.

## Expected Permission Matrix

### Data Fabric: ALL Layers Access

```
data_fabric:
  ├── bronze layer
  │   ├── read ✓
  │   ├── write ✓
  │   ├── execute ✓
  │   └── transform ✓
  ├── silver layer
  │   ├── read ✓
  │   ├── write ✓
  │   ├── execute ✓
  │   └── transform ✓
  ├── gold layer
  │   ├── read ✓
  │   ├── write ✓
  │   ├── execute ✓
  │   └── transform ✓
  └── ALL data categories: customer, product, transaction, inventory, ml_features
```

### Data Mesh: Silver+ Access

```
data_mesh:
  ├── bronze layer - ✗ DENIED
  ├── silver layer
  │   ├── read ✓
  │   ├── write ✓
  │   ├── publish ✓
  │   └── execute ✗
  ├── gold layer
  │   ├── read ✓
  │   ├── write ✓
  │   ├── publish ✓
  │   └── execute ✗
  └── Data categories: product, customer, domain_views, business_metrics
```

### Agentic AI: Gold Layer ML Operations

```
agentic_ai:
  ├── bronze layer - ✗ DENIED
  ├── silver layer - ✗ DENIED
  ├── gold layer
  │   ├── read ✓
  │   ├── write ✓
  │   ├── inference ✓
  │   ├── train ✓
  │   ├── transform ✗
  │   └── execute ✗
  └── Data categories: ml_features, embeddings, customer, product, personalization
```

## Running the Tests

### 1. Start the API Server

```bash
cd backend/src/services/data_architecture/api_server
python main.py
```

### 2. In another terminal, run the test commands above

```bash
# Test 1: Allowed access
curl -X POST "http://localhost:8000/api/governance/service-access-check?service_name=data_fabric&operation=read&layer=bronze&data_category=customer"

# Test 2: Denied access (wrong layer)
curl -X POST "http://localhost:8000/api/governance/service-access-check?service_name=data_mesh&operation=read&layer=bronze"

# Test 3: Get RBAC config
curl -X GET http://localhost:8000/api/governance/service-rbac

# Test 4: Get audit log
curl -X GET "http://localhost:8000/api/governance/service-rbac/audit-log?limit=50"
```

### 3. Verify responses

Ensure all responses include:
- ✅ `generated_at` timestamp
- ✅ Correct `access_granted` boolean
- ✅ Descriptive `reason` message
- ✅ All audit log entries have timestamps and details

## Next Steps: Middleware Integration

The RBACMiddleware is now registered in the FastAPI app. To enforce RBAC on specific endpoints:

```python
from pipeline.governance import require_rbac

@app.get('/api/medallion/{layer}/files')
@require_rbac(operation="read", layer_param="layer")
async def list_files(layer: str):
    # Protected endpoint
    pass
```

This will automatically check the `X-Service-Principal` header and validate access before executing the endpoint logic.

## Compliance & Audit Trail

All access checks (granted and denied) are logged to the RBAC audit log for compliance tracking. The audit log can be:
- Filtered by service name
- Limited to specific time ranges (future enhancement)
- Exported for compliance reports (future enhancement)

## Troubleshooting

### Issue: Service principal not found

**Solution**: Verify service name is one of:
- `data_fabric`
- `data_mesh`
- `agentic_ai`

### Issue: Access always denied

**Solution**: Check the permission matrix above. Each service has specific:
- Allowed layers (bronze/silver/gold)
- Allowed operations (read/write/execute/etc.)
- Allowed data categories

### Issue: Middleware not working

**Solution**: Verify RBACMiddleware is registered in main.py:
```python
from pipeline.governance import RBACMiddleware
app.add_middleware(RBACMiddleware)
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│  FastAPI Application                            │
│  ┌───────────────────────────────────────────┐  │
│  │ RBACMiddleware (registered)               │  │
│  │ - Checks X-Service-Principal header       │  │
│  │ - Validates service exists                │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────┐
│  Governance Module (service_rbac.py)            │
│  ┌───────────────────────────────────────────┐  │
│  │ ServiceRBACManager                        │  │
│  │ - 3 service principals pre-configured     │  │
│  │ - validate_access()                       │  │
│  │ - get_audit_log()                         │  │
│  │ - export_rbac_config()                    │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────┐
│  Data Access (medallion layers)                 │
│  - Bronze (raw, all services if permitted)      │
│  - Silver (cleaned, mesh/fabric only)           │
│  - Gold (curated, AI/mesh/fabric)               │
└─────────────────────────────────────────────────┘
```
