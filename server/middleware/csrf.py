from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CSRFOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, allowed_origins: list[str], auth_mode: str = "dev"):
        super().__init__(app)
        self.allowed_origins = set(allowed_origins)
        self.auth_mode = auth_mode

    async def dispatch(self, request: Request, call_next):
        if self.auth_mode in ("dev", "proxy"):
            return await call_next(request)

        if request.method in _SAFE_METHODS:
            return await call_next(request)

        origin = request.headers.get("Origin")
        if not origin or origin not in self.allowed_origins:
            return JSONResponse(
                status_code=403,
                content={"detail": "Origin header missing or not allowed"},
            )

        return await call_next(request)
