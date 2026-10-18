import os

from arbiter_mcp.server import create_mcp_server

api_url = os.environ.get("ARBITER_API_URL", "http://localhost:8400")
mcp = create_mcp_server(api_url=api_url)
mcp.run(transport="streamable-http", host="0.0.0.0", port=8401)
