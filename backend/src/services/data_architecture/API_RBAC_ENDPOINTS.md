"""
Add this code to backend/src/services/data_architecture/api_server/main.py
after the /api/governance/audit-log endpoint (around line 2740)

---

@app.get('/api/governance/service-rbac')
async def get_service_rbac_config():
    """
    Service-level RBAC configuration for Data Mesh, Data Fabric, and Agentic AI.
    Shows permissions for each service to access Azure data.
    """
    try:
        from pipeline.governance import get_rbac_manager
        
        rbac = get_rbac_manager()
        config = rbac.export_rbac_config()
        
        return {
            "generated_at": _utc_iso_now(),
            **config,
        }
    except Exception as exc:
        logger.error(f"Error getting RBAC config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post('/api/governance/service-access-check')
async def check_service_access(
    service_name: str = Query(..., description="Service name (data_fabric, data_mesh, agentic_ai)"),
    operation: str = Query(..., description="Operation type (read, write, execute, etc.)"),
    layer: str = Query(..., description="Medallion layer (bronze, silver, gold)"),
    data_category: str = Query("", description="Data category (optional)"),
):
    """
    Check if a service has access to perform an operation on a data layer.
    Used for validating service access before operations.
    """
    try:
        from pipeline.governance import get_rbac_manager
        
        rbac = get_rbac_manager()
        is_allowed, reason = rbac.validate_access(
            service_name=service_name,
            operation=operation,
            layer=layer,
            data_category=data_category,
        )
        
        return {
            "generated_at": _utc_iso_now(),
            "service_name": service_name,
            "operation": operation,
            "layer": layer,
            "data_category": data_category,
            "access_granted": is_allowed,
            "reason": reason,
        }
    except Exception as exc:
        logger.error(f"Error checking service access: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/api/governance/service-rbac/audit-log')
async def get_service_rbac_audit_log(
    service_name: Optional[str] = Query(None, description="Filter by service name (optional)"),
    limit: int = Query(100, description="Maximum entries to return", ge=1, le=1000),
):
    """
    Audit log for service access attempts.
    Shows all read/write operations by service with grant/deny status.
    """
    try:
        from pipeline.governance import get_rbac_manager
        
        rbac = get_rbac_manager()
        audit_log = rbac.get_audit_log(service_name=service_name)
        
        # Return latest entries
        return {
            "generated_at": _utc_iso_now(),
            "service_filter": service_name,
            "total_entries": len(audit_log),
            "entries": audit_log[-limit:] if audit_log else [],
        }
    except Exception as exc:
        logger.error(f"Error getting RBAC audit log: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

---
"""
