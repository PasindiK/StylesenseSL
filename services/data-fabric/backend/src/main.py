from fastapi import FastAPI

app = FastAPI(title="Data Fabric Service")


@app.get("/api/health/ping")
def health_ping():
    return {"status": "healthy", "service": "data-fabric"}


@app.get("/api/module")
def module_info():
    return {
        "module": "data-fabric",
        "description": "Shop collection data fabric service",
        "status": "ready"
    }
