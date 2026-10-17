# tests/unit/test_mcp.py
import pytest
from arbiter_mcp.client import ArbiterClient
from arbiter_mcp.server import create_mcp_server


def test_client_init():
    client = ArbiterClient(base_url="http://localhost:8400")
    assert client._base_url == "http://localhost:8400"


@pytest.mark.asyncio
async def test_mcp_server_has_seven_tools():
    server = create_mcp_server(api_url="http://localhost:8400")
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "check_workload_status", "list_workloads_by_state",
        "check_compliance", "verify_artifact", "gate_check",
        "query_audit_log", "backend_health",
    }
    assert expected.issubset(tool_names)
