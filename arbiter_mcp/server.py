# arbiter_mcp/server.py
from fastmcp import FastMCP
from arbiter_mcp.client import ArbiterClient


def create_mcp_server(api_url: str = "http://localhost:8400") -> FastMCP:
    mcp = FastMCP("arbiter-hub-mcp")
    client = ArbiterClient(base_url=api_url)

    @mcp.tool()
    async def check_workload_status(workload_id: str) -> dict:
        """Check attestation status and state of a workload."""
        return await client.get_workload(workload_id)

    @mcp.tool()
    async def list_workloads_by_state(state: str | None = None) -> dict:
        """List workloads, optionally filtered by state (registered, attesting, healthy, stale, failed, under_remediation, revoked)."""
        return await client.list_workloads(state=state)

    @mcp.tool()
    async def check_compliance(workload_id: str) -> dict:
        """Check if a workload is compliant with active policies."""
        return await client.check_compliance(workload_id)

    @mcp.tool()
    async def verify_artifact(artifact_ref: str) -> dict:
        """Verify a cosign signature on a container image or artifact."""
        return await client.verify_artifact(artifact_ref)

    @mcp.tool()
    async def gate_check(workload_id: str) -> dict:
        """Full gate evaluation: compliance + state + attestation currency."""
        workload = await client.get_workload(workload_id)
        compliance = await client.check_compliance(workload_id)
        return {
            "workload_id": workload_id,
            "gate_passed": (
                workload.get("current_state") == "healthy"
                and compliance.get("compliant", False)
            ),
            "state": workload.get("current_state"),
            "compliance": compliance,
        }

    @mcp.tool()
    async def query_audit_log(actor: str | None = None, action: str | None = None) -> dict:
        """Query the attestation audit log."""
        return await client.query_audit(actor=actor, action=action)

    @mcp.tool()
    async def backend_health() -> dict:
        """Check health status of all attestation backends."""
        return await client.backend_health()

    return mcp
