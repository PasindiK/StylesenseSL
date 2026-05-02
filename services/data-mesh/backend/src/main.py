from fastapi import FastAPI

app = FastAPI(title="Data Mesh Service")


@app.get("/api/health")
def health():
    return {"status": "healthy", "service": "data-mesh"}


@app.get("/api/module")
def module_info():
    return {
        "module": "data-mesh",
        "description": "Shop-wise data mesh service",
        "status": "ready"
    }
