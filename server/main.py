from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.api import attestation, audit, health, kbs, signing, workloads
from server.backends.base import BackendRegistry
from server.config import settings
from server.telemetry.otel import add_metrics_endpoint, setup_telemetry


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
    setup_telemetry(app, settings)
    add_metrics_endpoint(app)
    app.include_router(health.router, tags=["health"])
    app.include_router(workloads.router, tags=["workloads"])
    app.include_router(audit.router, tags=["audit"])
    app.include_router(attestation.router, tags=["attestation"])
    app.include_router(signing.router, tags=["signing"])
    app.include_router(kbs.router, tags=["kbs"])
    return app
