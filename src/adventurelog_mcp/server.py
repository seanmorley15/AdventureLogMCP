"""The MCP server: tool registration, the /health route and the HTTP app."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__
from .config import get_settings
from .tools import account, collection_items, collections, locations, places

INSTRUCTIONS = """\
AdventureLog is a self-hosted travel log. Vocabulary:
- A *location* is a saved place the user has visited or wants to visit.
- A *collection* is a folder of locations and can also be a dated plan with a day-by-day itinerary.
  It also holds lodgings, transportations, notes and checklists. Never call a collection a "trip".
- A *place* is an external search result (not saved yet); saving one creates a location.
Search before creating, so you do not add duplicates.
"""


def build_server() -> MCPServer:
    mcp = MCPServer("AdventureLog", instructions=INSTRUCTIONS, version=__version__)
    for module in (account, locations, places, collections, collection_items):
        module.register(mcp)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "version": __version__})

    return mcp


def build_http_app():
    """The Streamable HTTP app (stateless: every request carries the caller's own key)."""
    settings = get_settings()
    hosts = settings.allowed_hosts
    security = (
        TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=["*"])
        if hosts
        else TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
    return build_server().streamable_http_app(
        json_response=True, stateless_http=True, host=settings.mcp_host, transport_security=security
    )
