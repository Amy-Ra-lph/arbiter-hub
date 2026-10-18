from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.api import attestation, audit, health, kbs, signing, workloads
from server.backends.base import BackendRegistry
from server.config import settings
from server.telemetry.otel import add_metrics_endpoint, setup_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry = BackendRegistry()
    if settings.keylime_verifier_url:
        from server.backends.keylime import KeylimeBackend

        registry.register(
            "keylime",
            KeylimeBackend(
                verifier_url=settings.keylime_verifier_url,
                ca_cert=settings.keylime_ca_cert,
                client_cert=settings.keylime_client_cert,
                client_key=settings.keylime_client_key,
            ),
        )
    app.state.backend_registry = registry
    yield


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
