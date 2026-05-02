from fastapi import FastAPI

app = FastAPI(title="Data Architecture Service")


@app.get("/api/health")
def health():
    return {"status": "healthy", "service": "data-architecture"}


@app.get("/api/module")
def module_info():
    return {
        "module": "data-architecture",
        "description": "Data architecture and governance service",
        "status": "ready"
    }
