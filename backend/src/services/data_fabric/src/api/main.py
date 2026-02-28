"""API main application."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from configs.settings import get_settings
from .routes import ingestion, preprocessing, validation, metadata, ml, health
from .middleware.auth import AuthMiddleware

logger = logging.getLogger(__name__)

settings = get_settings()


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title=settings.api_title,
        version="1.0.0",
        description="Data Fabric RESTful API Service",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes
    app.include_router(health.router, prefix="/api/health", tags=["Health"])
    app.include_router(ingestion.router, prefix="/api/ingestion", tags=["Ingestion"])
    app.include_router(preprocessing.router, prefix="/api/preprocessing", tags=["Preprocessing"])
    app.include_router(validation.router, prefix="/api/validation", tags=["Validation"])
    app.include_router(metadata.router, prefix="/api/metadata", tags=["Metadata"])
    app.include_router(ml.router, prefix="/api/ml", tags=["ML"])

    # Global exception handler
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        """Handle HTTP exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )

    @app.on_event("startup")
    async def startup_event():
        """Startup event."""
        logger.info("Data Fabric API starting up")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Shutdown event."""
        logger.info("Data Fabric API shutting down")

    return app


app = create_app()
