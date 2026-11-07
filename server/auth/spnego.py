"""SPNEGO/Kerberos authentication for machine-to-machine service auth.

Uses the host's HTTP/ service keytab to validate Negotiate tokens from
IPA-enrolled nodes. Issues local JWTs on success so callers can use
standard Bearer auth for subsequent requests.

Requires: python3-gssapi (optional dependency — import guarded).
Enable via ARBITER_SPNEGO_ENABLED=true + ARBITER_SPNEGO_KEYTAB path.
"""

import base64
import logging
import os

from server.auth.models import CallerIdentity, Role

logger = logging.getLogger(__name__)

try:
    import gssapi

    GSSAPI_AVAILABLE = True
except ImportError:
    GSSAPI_AVAILABLE = False
    logger.info("gssapi not installed — SPNEGO auth unavailable")


# Principal-to-role mapping: host/ principals get service role, others get viewer
_PRINCIPAL_ROLE_MAP = {
    "host/": [Role.ADMIN],
    "HTTP/": [Role.ADMIN],
    "admin": [Role.ADMIN],
}


def _roles_for_principal(principal: str) -> list[str]:
    for prefix, roles in _PRINCIPAL_ROLE_MAP.items():
        if principal.startswith(prefix) or principal.split("@")[0] == prefix:
            return roles
    return ["attestation-viewer"]


class SPNEGOProvider:
    def __init__(self, keytab_path: str, service_principal: str | None = None):
        if not GSSAPI_AVAILABLE:
            raise RuntimeError("gssapi package not installed")
        if not os.path.isfile(keytab_path):
            raise FileNotFoundError(f"keytab not found: {keytab_path}")

        self._keytab_path = keytab_path
        os.environ["KRB5_KTNAME"] = keytab_path

        if service_principal:
            self._server_name = gssapi.Name(
                service_principal, gssapi.NameType.kerberos_principal
            )
        else:
            self._server_name = None

        self._creds = gssapi.Credentials(
            name=self._server_name,
            usage="accept",
        )
        logger.info(
            "SPNEGO provider initialized: keytab=%s principal=%s",
            keytab_path,
            service_principal or "(default)",
        )

    def validate_token(self, negotiate_token: str) -> tuple[str, str | None]:
        """Validate a base64 SPNEGO token. Returns (client_principal, response_token)."""
        in_token = base64.b64decode(negotiate_token)

        ctx = gssapi.SecurityContext(creds=self._creds, usage="accept")
        out_token = ctx.step(in_token)

        if not ctx.complete:
            raise ValueError("SPNEGO context not complete after single step")

        client_principal = str(ctx.initiator_name)
        response_b64 = base64.b64encode(out_token).decode() if out_token else None

        logger.info("SPNEGO auth succeeded: %s", client_principal)
        return client_principal, response_b64

    def build_identity(self, principal: str) -> CallerIdentity:
        """Map a Kerberos principal to a CallerIdentity."""
        short_name = principal.split("@")[0]
        return CallerIdentity(
            principal=principal,
            actor_type="service" if "/" in short_name else "user",
            roles=_roles_for_principal(short_name),
            scopes=["openid", "profile", "attestation-admin"],
        )
