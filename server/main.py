from fastapi import FastAPI
from contextlib import asynccontextmanager
from server.api import workloads, audit, health, attestation, signing
from server.backends.base import BackendRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: DB engine, backends, scheduler
    app.state.backend_registry = BackendRegistry()
    yield
    # shutdown: close connections


def create_app() -> FastAPI:
    app = FastAPI(
        title="Arbiter Hub",
        description="Federation hub for workload attestation",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router, tags=["health"])
    app.include_router(workloads.router, tags=["workloads"])
    app.include_router(audit.router, tags=["audit"])
    app.include_router(attestation.router, tags=["attestation"])
    app.include_router(signing.router, tags=["signing"])
    return app
