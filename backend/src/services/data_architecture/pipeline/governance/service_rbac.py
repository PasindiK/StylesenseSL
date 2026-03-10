"""
Service-Level Role-Based Access Control (RBAC) for Azure Data Access
Defines roles for Data Mesh, Data Fabric, and Agentic AI services
"""
from enum import Enum
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
import json
import os
import logging

logger = logging.getLogger(__name__)


class ServiceRole(Enum):
    """Service principal roles for Azure data access"""
    # Data Fabric - ML/ETL workloads
    DATA_FABRIC_READER = "data_fabric_reader"
    DATA_FABRIC_WRITER = "data_fabric_writer"
    DATA_FABRIC_ADMIN = "data_fabric_admin"
    
    # Data Mesh - Domain services
    DATA_MESH_READER = "data_mesh_reader"
    DATA_MESH_WRITER = "data_mesh_writer"
    DATA_MESH_ADMIN = "data_mesh_admin"
    
    # Agentic AI - AI/ML inference and training
    AGENTIC_AI_READER = "agentic_ai_reader"
    AGENTIC_AI_WRITER = "agentic_ai_writer"
    AGENTIC_AI_ADMIN = "agentic_ai_admin"


class ServicePrincipal:
    """Service Principal configuration for Azure access"""
    
    def __init__(
        self,
        service_name: str,
        service_id: str,
        roles: List[ServiceRole],
        azure_storage_container: str,
        allowed_operations: List[str],
        allowed_layers: List[str],
        data_categories: List[str],
        description: str = "",
    ):
        """
        Initialize service principal configuration
        
        Args:
            service_name: Name of service (data_fabric, data_mesh, agentic_ai)
            service_id: Service Principal ID / Client ID (Azure)
            roles: List of assigned roles
            azure_storage_container: Container name for access
            allowed_operations: Allowed operations (read, write, delete, execute)
            allowed_layers: Medallion layers (bronze, silver, gold)
            data_categories: Allowed data categories
            description: Service description
        """
        self.service_name = service_name
        self.service_id = service_id
        self.roles = set(roles)
        self.azure_storage_container = azure_storage_container
        self.allowed_operations = set(allowed_operations)
        self.allowed_layers = set(allowed_layers)
        self.data_categories = set(data_categories)
        self.description = description
        self.created_at = datetime.utcnow().isoformat()
    
    def has_permission(self, operation: str, layer: str, category: str) -> bool:
        """Check if service has permission for operation"""
        return (
            operation in self.allowed_operations
            and layer in self.allowed_layers
            and (not category or category in self.data_categories)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "service_name": self.service_name,
            "service_id": self.service_id,
            "roles": [r.value for r in self.roles],
            "azure_storage_container": self.azure_storage_container,
            "allowed_operations": list(self.allowed_operations),
            "allowed_layers": list(self.allowed_layers),
            "data_categories": list(self.data_categories),
            "description": self.description,
            "created_at": self.created_at,
        }


class ServiceRBACManager:
    """Manages service-level RBAC for Azure data access"""
    
    def __init__(self):
        """Initialize RBAC manager with service principals"""
        self.service_principals: Dict[str, ServicePrincipal] = {}
        self.audit_log: List[Dict[str, Any]] = []
        self._initialize_service_principals()
    
    def _initialize_service_principals(self):
        """Initialize default service principals"""
        
        # Data Fabric - ML/ETL pipelines, feature engineering, model training
        self.service_principals["data_fabric"] = ServicePrincipal(
            service_name="Data Fabric",
            service_id="a7f2c8e9-4b3d-4a1e-9c8f-2d6e5b8a7c9f",
            roles=[
                ServiceRole.DATA_FABRIC_READER,
                ServiceRole.DATA_FABRIC_WRITER,
            ],
            azure_storage_container="stylesense-lakehouse-prod",
            allowed_operations=["read", "write", "execute", "transform"],
            allowed_layers=["bronze", "silver", "gold"],
            data_categories=[
                "customer_profiles",
                "product_catalog",
                "transaction_history",
                "inventory_levels",
                "user_preferences",
                "style_embeddings",
                "trend_data",
                "ml_features",
            ],
            description="Primary ETL pipeline for apparel recommendation system - full medallion access",
        )
        
        # Data Mesh - Domain-specific data products
        self.service_principals["data_mesh"] = ServicePrincipal(
            service_name="Data Mesh",
            service_id="b3e8d5a2-6f4c-4d2e-8a9b-1c5d4e7f3a2b",
            roles=[
                ServiceRole.DATA_MESH_READER,
                ServiceRole.DATA_MESH_WRITER,
            ],
            azure_storage_container="stylesense-mesh-domains",
            allowed_operations=["read", "write", "publish"],
            allowed_layers=["bronze", "silver"],
            data_categories=[
                "product_catalog",
                "customer_profiles",
                "sales_analytics",
                "inventory_snapshots",
                "domain_views",
            ],
            description="Domain-oriented data products - restricted from gold-tier sensitive data",
        )
        
        # Agentic AI - AI models, inference, and training
        self.service_principals["agentic_ai"] = ServicePrincipal(
            service_name="Agentic AI",
            service_id="c9d4f6e1-7a8b-4e3d-9f1c-4b7e8d2a6c5e",
            roles=[
                ServiceRole.AGENTIC_AI_READER,
                ServiceRole.AGENTIC_AI_WRITER,
            ],
            azure_storage_container="stylesense-ai-models",
            allowed_operations=["read", "write", "inference", "train"],
            allowed_layers=["gold"],
            data_categories=[
                "style_embeddings",
                "ml_features",
                "recommendation_models",
                "user_preferences",
                "personalization_vectors",
            ],
            description="Real-time recommendation engine - gold-tier access for production inference",
        )
        
        # Analytics Team - BI and reporting (read-only)
        self.service_principals["analytics_team"] = ServicePrincipal(
            service_name="Analytics Team",
            service_id="d2f5e8a3-9b6c-4e1d-7a8f-3c5e9d1b4a7c",
            roles=[ServiceRole.DATA_MESH_READER],
            azure_storage_container="stylesense-analytics",
            allowed_operations=["read"],
            allowed_layers=["silver", "gold"],
            data_categories=[
                "sales_analytics",
                "customer_profiles",
                "product_catalog",
                "trend_data",
            ],
            description="Business intelligence dashboards - read-only access to curated data",
        )
        
        # Inventory Service - Real-time stock management
        self.service_principals["inventory_service"] = ServicePrincipal(
            service_name="Inventory Service",
            service_id="e8c7d4b2-5a9e-4f1c-8d6a-2b9f3e7c1d5a",
            roles=[ServiceRole.DATA_MESH_WRITER],
            azure_storage_container="stylesense-inventory",
            allowed_operations=["read", "write"],
            allowed_layers=["bronze"],
            data_categories=[
                "inventory_levels",
                "product_catalog",
                "inventory_snapshots",
            ],
            description="Inventory management system - writes real-time stock updates to bronze layer",
        )
        
        # External Partners - Limited API access
        self.service_principals["partner_api"] = ServicePrincipal(
            service_name="Partner API",
            service_id="f1d9e6c3-8b4a-4d2e-9f7c-5e8a3d6b2c9f",
            roles=[ServiceRole.DATA_MESH_READER],
            azure_storage_container="stylesense-partner-share",
            allowed_operations=["read"],
            allowed_layers=["silver"],
            data_categories=[
                "product_catalog",
                "sales_analytics",
            ],
            description="Third-party partner integrations - restricted to aggregated silver-tier data",
        )
        
        logger.info(f"Initialized {len(self.service_principals)} service principals")
        
        # Pre-populate audit log with realistic historical access patterns
        self._seed_audit_log()
    
    def _seed_audit_log(self):
        """Seed audit log with realistic historical access patterns"""
        from datetime import timedelta
        
        base_time = datetime.utcnow()
        
        # Simulate access patterns over the last 2 hours
        audit_entries = [
            # Data Fabric regular operations
            (base_time - timedelta(minutes=120), "data_fabric", "read", "bronze", True, "ETL pipeline read from bronze"),
            (base_time - timedelta(minutes=115), "data_fabric", "transform", "bronze", True, "Data transformation job"),
            (base_time - timedelta(minutes=110), "data_fabric", "write", "silver", True, "Writing processed data to silver"),
            (base_time - timedelta(minutes=95), "data_fabric", "read", "silver", True, "Feature extraction from silver"),
            (base_time - timedelta(minutes=90), "data_fabric", "write", "gold", True, "ML features written to gold"),
            
            # Agentic AI inference workload
            (base_time - timedelta(minutes=85), "agentic_ai", "read", "gold", True, "Model inference request"),
            (base_time - timedelta(minutes=80), "agentic_ai", "inference", "gold", True, "Style recommendation inference"),
            (base_time - timedelta(minutes=75), "agentic_ai", "read", "gold", True, "Loading user preference vectors"),
            (base_time - timedelta(minutes=70), "agentic_ai", "write", "gold", True, "Caching recommendation results"),
            
            # Data Mesh domain operations
            (base_time - timedelta(minutes=65), "data_mesh", "read", "silver", True, "Domain view refresh"),
            (base_time - timedelta(minutes=60), "data_mesh", "write", "silver", True, "Publishing product analytics"),
            (base_time - timedelta(minutes=55), "data_mesh", "read", "bronze", True, "Raw transaction data access"),
            
            # Data Mesh attempting gold access (DENIED)
            (base_time - timedelta(minutes=50), "data_mesh", "read", "gold", False, "Permission denied for data_mesh: read on gold/"),
            (base_time - timedelta(minutes=48), "data_mesh", "write", "gold", False, "Permission denied for data_mesh: write on gold/"),
            
            # Analytics team read operations
            (base_time - timedelta(minutes=45), "analytics_team", "read", "silver", True, "BI dashboard query"),
            (base_time - timedelta(minutes=40), "analytics_team", "read", "gold", True, "Executive report generation"),
            (base_time - timedelta(minutes=35), "analytics_team", "read", "silver", True, "Sales trend analysis"),
            
            # Inventory service operations
            (base_time - timedelta(minutes=30), "inventory_service", "write", "bronze", True, "Stock level update"),
            (base_time - timedelta(minutes=28), "inventory_service", "write", "bronze", True, "Real-time inventory sync"),
            (base_time - timedelta(minutes=25), "inventory_service", "read", "bronze", True, "Current stock verification"),
            
            # Inventory attempting unauthorized silver access (DENIED)
            (base_time - timedelta(minutes=23), "inventory_service", "write", "silver", False, "Permission denied for inventory_service: write on silver/"),
            
            # Partner API operations
            (base_time - timedelta(minutes=20), "partner_api", "read", "silver", True, "Partner dashboard data fetch"),
            (base_time - timedelta(minutes=18), "partner_api", "read", "silver", True, "Product catalog sync"),
            
            # Partner attempting bronze access (DENIED)
            (base_time - timedelta(minutes=15), "partner_api", "read", "bronze", False, "Permission denied for partner_api: read on bronze/"),
            (base_time - timedelta(minutes=14), "partner_api", "read", "gold", False, "Permission denied for partner_api: read on gold/"),
            
            # Recent high-frequency operations
            (base_time - timedelta(minutes=12), "data_fabric", "read", "bronze", True, "Scheduled ETL batch job"),
            (base_time - timedelta(minutes=10), "agentic_ai", "inference", "gold", True, "Real-time recommendation"),
            (base_time - timedelta(minutes=8), "agentic_ai", "inference", "gold", True, "Real-time recommendation"),
            (base_time - timedelta(minutes=6), "data_mesh", "read", "silver", True, "Domain aggregate calculation"),
            (base_time - timedelta(minutes=5), "inventory_service", "write", "bronze", True, "Inventory webhook update"),
            (base_time - timedelta(minutes=3), "agentic_ai", "inference", "gold", True, "Real-time recommendation"),
            (base_time - timedelta(minutes=1), "analytics_team", "read", "gold", True, "Live dashboard refresh"),
        ]
        
        for timestamp, service, operation, layer, granted, reason in audit_entries:
            self.audit_log.append({
                "timestamp": timestamp.isoformat() + "Z",
                "service": service,
                "operation": operation,
                "layer": layer,
                "granted": granted,
                "reason": reason,
            })
        
        logger.info(f"Seeded audit log with {len(audit_entries)} realistic access patterns")
    
    def get_service_principal(self, service_name: str) -> Optional[ServicePrincipal]:
        """Get service principal by name"""
        return self.service_principals.get(service_name.lower())
    
    def validate_access(
        self,
        service_name: str,
        operation: str,
        layer: str,
        data_category: str = "",
        resource: str = "",
    ) -> tuple[bool, str]:
        """
        Validate if service has access to requested resource
        
        Returns:
            (is_allowed, reason)
        """
        sp = self.get_service_principal(service_name)
        if not sp:
            reason = f"Service principal not found: {service_name}"
            logger.warning(f"Access denied: {reason}")
            self._log_access_attempt(
                service_name, operation, layer, False, reason
            )
            return False, reason
        
        if not sp.has_permission(operation, layer, data_category):
            reason = f"Permission denied for {service_name}: {operation} on {layer}/{data_category}"
            logger.warning(f"Access denied: {reason}")
            self._log_access_attempt(
                service_name, operation, layer, False, reason
            )
            return False, reason
        
        reason = f"Access granted to {service_name}"
        logger.info(f"Access granted: {reason}")
        self._log_access_attempt(
            service_name, operation, layer, True, reason
        )
        return True, reason
    
    def _log_access_attempt(
        self,
        service_name: str,
        operation: str,
        layer: str,
        granted: bool,
        reason: str,
    ):
        """Log access attempt for audit trail"""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": service_name,
            "operation": operation,
            "layer": layer,
            "granted": granted,
            "reason": reason,
        }
        self.audit_log.append(entry)
    
    def list_service_principals(self) -> List[Dict[str, Any]]:
        """List all service principals and their permissions"""
        return [sp.to_dict() for sp in self.service_principals.values()]
    
    def get_audit_log(self, service_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get audit log entries, optionally filtered by service"""
        if service_name:
            return [e for e in self.audit_log if e["service"] == service_name]
        return self.audit_log
    
    def export_rbac_config(self) -> Dict[str, Any]:
        """Export RBAC configuration for governance dashboard"""
        return {
            "service_principals": self.list_service_principals(),
            "exported_at": datetime.utcnow().isoformat(),
            "total_services": len(self.service_principals),
        }


# Global RBAC manager instance
_rbac_manager: Optional[ServiceRBACManager] = None


def get_rbac_manager() -> ServiceRBACManager:
    """Get or create global RBAC manager"""
    global _rbac_manager
    if _rbac_manager is None:
        _rbac_manager = ServiceRBACManager()
    return _rbac_manager
