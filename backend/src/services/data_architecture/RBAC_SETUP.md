# Service-Level Role-Based Access Control (RBAC)

## Overview

This document describes the RBAC implementation for service-level access to Azure data. Three services have specific roles:

- **Data Fabric** - ML/ETL pipelines and feature engineering
- **Data Mesh** - Domain-specific data products  
- **Agentic AI** - AI models, inference, and training

## Service Principals

### 1. Data Fabric
**Service ID**: `sp_data_fabric_001`  
**Container**: `data-fabric`

**Roles:**
- `data_fabric_reader` - Read data
- `data_fabric_writer` - Write transformed data
- `data_fabric_admin` - Administrative access

**Permissions:**
- **Operations**: read, write, execute, transform
- **Layers**: bronze, silver, gold
- **Data Categories**: 
  - customer_data
  - product_data
  - transaction_data
  - inventory_data
  - ml_features

**Use Cases:**
- Read raw data from bronze layer
- Transform and clean data (silver)
- Generate ML features (gold)
- Train models

---

### 2. Data Mesh
**Service ID**: `sp_data_mesh_001`  
**Container**: `data-mesh`

**Roles:**
- `data_mesh_reader` - Read data
- `data_mesh_writer` - Write domain views
- `data_mesh_admin` - Administrative access

**Permissions:**
- **Operations**: read, write, publish
- **Layers**: silver, gold
- **Data Categories**:
  - product_data
  - customer_data
  - domain_views
  - business_metrics

**Use Cases:**
- Publish domain-oriented data products
- Create curated views for business users
- Generate business metrics

---

### 3. Agentic AI
**Service ID**: `sp_agentic_ai_001`  
**Container**: `agentic-ai`

**Roles:**
- `agentic_ai_reader` - Read features and data
- `agentic_ai_writer` - Write predictions and embeddings
- `agentic_ai_admin` - Administrative access

**Permissions:**
- **Operations**: read, write, inference, train
- **Layers**: gold (curated features only)
- **Data Categories**:
  - ml_features
  - embeddings
  - customer_data
  - product_data
  - personalization_data

**Use Cases:**
- Read features from gold layer
- Run inference on customer data
- Generate embeddings
- Train AI models

---

## Implementation

### Python Usage

```python
from pipeline.governance import get_rbac_manager, ServiceRole

# Get RBAC manager
rbac = get_rbac_manager()

# Check access
is_allowed, reason = rbac.validate_access(
    service_name="data_fabric",
    operation="write",
    layer="gold",
    data_category="ml_features"
)

if is_allowed:
    print(f"✓ Access granted: {reason}")
else:
    print(f"✗ Access denied: {reason}")
```

### API Usage

**With service principal header:**

```bash
curl -X GET "http://localhost:8000/api/medallion/gold/files" \
  -H "X-Service-Principal: data_fabric"
```

---

## Audit Trail

All access attempts are logged with:
- Timestamp
- Service name
- Operation type
- Layer accessed
- Whether access was granted/denied
- Reason

Access logs available via:
```python
rbac = get_rbac_manager()
logs = rbac.get_audit_log(service_name="data_fabric")
```

---

## Configuration

Service principals are initialized in `ServiceRBACManager.__init__()` with:
1. Service identification (name, ID)
2. Assigned roles
3. Azure storage container
4. Allowed operations
5. Allowed medallion layers
6. Allowed data categories

### Modifying Access

To modify permissions, update `service_rbac.py`:

```python
self.service_principals["service_name"] = ServicePrincipal(
    service_name="Service Name",
    service_id="sp_service_001",
    roles=[ServiceRole.SERVICE_READER, ServiceRole.SERVICE_WRITER],
    azure_storage_container="container_name",
    allowed_operations=["read", "write"],
    allowed_layers=["bronze", "silver", "gold"],
    data_categories=["category1", "category2"],
    description="Service description"
)
```

---

## Security Considerations

1. **Service Principal Secrets**: Stored securely in Azure Key Vault (not in code)
2. **Token Validation**: Tokens should be validated against Azure AD
3. **Audit Trail**: All access attempts are logged for compliance
4. **Least Privilege**: Each service gets minimum required permissions
5. **Layer Segregation**: 
   - Data Fabric: All layers (processing)
   - Data Mesh: Silver/Gold (curated)
   - Agentic AI: Gold only (features)

---

## Governance Dashboard Integration

Service principals and their permissions are exposed via:

**Endpoint:** `/api/governance/service-rbac`

**Response:**
```json
{
  "service_principals": [
    {
      "service_name": "Data Fabric",
      "service_id": "sp_data_fabric_001",
      "roles": ["data_fabric_reader", "data_fabric_writer"],
      "allowed_operations": ["read", "write", "execute", "transform"],
      "allowed_layers": ["bronze", "silver", "gold"],
      "data_categories": [...]
    },
    ...
  ],
  "exported_at": "2026-03-09T21:00:00Z",
  "total_services": 3
}
```

---

## Next Steps

1. ✅ Define service principals and roles
2. ⏳ Integrate with Azure AD for token validation
3. ⏳ Sync service principals with Azure Entra ID
4. ⏳ Configure Azure RBAC roles for storage containers
5. ⏳ Add dashboard visualization for access controls

See `pipeline/governance/service_rbac.py` for implementation.
