"""
RBAC Middleware for service-level access control
Validates service principals accessing Azure data through the API
"""
from typing import Optional, Callable
from fastapi import Request, HTTPException, Header, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from functools import wraps
import logging
from .service_rbac import get_rbac_manager

logger = logging.getLogger(__name__)


class RBACMiddleware(BaseHTTPMiddleware):
    """RBAC validation middleware for FastAPI"""
    
    async def dispatch(self, request: Request, call_next):
        """Process request and validate service principal"""
        # Extract service identifier from headers
        service_name = request.headers.get("X-Service-Principal")
        
        if service_name:
            # Store in request state for downstream use
            request.state.service_name = service_name
            request.state.rbac_manager = get_rbac_manager()
            
            logger.debug(f"Request from service: {service_name}")
        
        response = await call_next(request)
        return response


def require_rbac(operation: str, layer: str, data_category: str = ""):
    """
    Decorator to require RBAC validation for endpoints
    
    Args:
        operation: Operation type (read, write, execute, etc.)
        layer: Medallion layer (bronze, silver, gold)
        data_category: Data category being accessed
    
    Usage:
        @app.get("/api/data/{layer}")
        @require_rbac(operation="read", layer="gold", data_category="customer_data")
        async def get_gold_data(request: Request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            service_name = getattr(request.state, "service_name", None)
            rbac_manager = getattr(request.state, "rbac_manager", None)
            
            if not rbac_manager:
                rbac_manager = get_rbac_manager()
            
            # If no service principal specified, allow (for backward compat)
            if not service_name:
                logger.warning("No service principal in request headers")
                return await func(request, *args, **kwargs)
            
            # Validate access
            is_allowed, reason = rbac_manager.validate_access(
                service_name=service_name,
                operation=operation,
                layer=layer,
                data_category=data_category,
                resource=request.url.path,
            )
            
            if not is_allowed:
                logger.error(f"RBAC validation failed: {reason}")
                raise HTTPException(
                    status_code=403,
                    detail=f"Access forbidden: {reason}",
                )
            
            logger.info(f"RBAC validation passed for {service_name}: {reason}")
            request.state.rbac_validated = True
            
            return await func(request, *args, **kwargs)
        
        return wrapper
    
    return decorator


def get_service_principal_header(
    x_service_principal: Optional[str] = Header(None)
) -> Optional[str]:
    """Dependency for extracting service principal from headers"""
    return x_service_principal


def validate_service_access(
    operation: str,
    layer: str,
    data_category: str = "",
) -> Callable:
    """
    Dependency for validating service access
    
    Usage:
        @app.get("/api/data")
        async def get_data(
            validated: bool = Depends(validate_service_access("read", "gold"))
        ):
            ...
    """
    async def validator(
        request: Request,
        service_principal: Optional[str] = Depends(get_service_principal_header),
    ) -> bool:
        if not service_principal:
            return True  # Allow requests without service principal
        
        rbac_manager = get_rbac_manager()
        is_allowed, reason = rbac_manager.validate_access(
            service_name=service_principal,
            operation=operation,
            layer=layer,
            data_category=data_category,
            resource=request.url.path,
        )
        
        if not is_allowed:
            raise HTTPException(status_code=403, detail=reason)
        
        return is_allowed
    
    return validator
