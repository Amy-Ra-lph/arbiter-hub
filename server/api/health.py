from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "arbiter-hub", "version": "0.1.0"}


@router.get("/backends")
async def backends(request: Request):
    # BackendRegistry is available in app.state (if lifespan ran)
    registry = getattr(request.app.state, 'backend_registry', None)
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
