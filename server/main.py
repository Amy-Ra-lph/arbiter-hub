from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from server.api import (
    alerts,
    attestation,
    audit,
    auth_config,
    health,
    kbs,
    signing,
    webhooks,
    workloads,
)
from server.backends.base import BackendRegistry
from server.config import settings
from server.middleware.csrf import CSRFOriginMiddleware
from server.state.scheduler import StalenessScheduler
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
    if settings.falco_healthz_url:
        from server.backends.falco import FalcoBackend

        registry.register(
            "falco",
            FalcoBackend(healthz_url=settings.falco_healthz_url),
        )
    if settings.cosign_public_key:
        from server.backends.cosign import CosignBackend

        registry.register(
            "cosign",
            CosignBackend(
                cosign_binary=settings.cosign_binary,
                rekor_url=settings.rekor_url,
                fulcio_url=settings.rhtas_fulcio_url,
                tuf_root=settings.rhtas_tuf_root,
                public_key=settings.cosign_public_key,
            ),
        )
    app.state.backend_registry = registry

    scheduler = StalenessScheduler(interval_seconds=30, registry=registry)
    scheduler.start()
    app.state.staleness_scheduler = scheduler

    yield

    await scheduler.stop()


limiter = Limiter(key_func=get_remote_address)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Arbiter Hub",
        description="Federation hub for workload attestation",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CSRFOriginMiddleware,
        allowed_origins=settings.cors_allowed_origins,
        auth_mode=settings.auth_mode,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Caller-Principal",
            "X-Caller-Type",
            "X-Caller-Roles",
            "X-Caller-Scopes",
        ],
        allow_credentials=False,
    )

    setup_telemetry(app, settings)
    add_metrics_endpoint(app)
    app.include_router(auth_config.router, tags=["auth"])
    app.include_router(health.router, tags=["health"])
    app.include_router(workloads.router, tags=["workloads"])
    app.include_router(audit.router, tags=["audit"])
    app.include_router(attestation.router, tags=["attestation"])
    app.include_router(alerts.router, tags=["alerts"])
    app.include_router(webhooks.router, tags=["webhooks"])
    app.include_router(signing.router, tags=["signing"])
    app.include_router(kbs.router, tags=["kbs"])
    return app
