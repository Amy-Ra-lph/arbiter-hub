import socket
from fastapi import APIRouter, Request

router = APIRouter()

NODE_ID = socket.gethostname()


@router.get("/health")
async def health(request: Request):
    registry = getattr(request.app.state, "backend_registry", None)
    backend_count = 0
    backends_healthy = True
    if registry:
        results = await registry.health_all()
        backend_count = len(results)
        backends_healthy = all(h.healthy for h in results.values())
    return {
        "status": "ok",
        "service": "arbiter-hub",
        "version": "0.1.0",
        "node_id": NODE_ID,
        "backends_healthy": backends_healthy,
        "backend_count": backend_count,
    }


@router.get("/backends")
async def backends(request: Request):
    # BackendRegistry is available in app.state (if lifespan ran)
    registry = getattr(request.app.state, "backend_registry", None)
    if not registry:
        # If lifespan hasn't run (e.g., in tests), return empty
        return {}
    health_results = await registry.health_all()
    # Convert BackendHealth dataclasses to dicts
    return {
        name: {
            "healthy": h.healthy,
            "backend": h.backend,
            "last_check": h.last_check.isoformat(),
            "detail": h.detail,
        }
        for name, h in health_results.items()
    }
