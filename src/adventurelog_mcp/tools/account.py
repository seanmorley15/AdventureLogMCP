"""Who is connected, and what this AdventureLog server supports."""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer

from ..auth import api
from ._common import READ_ONLY


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def whoami(ctx: Context) -> dict:
        """Check the connection: who the API key belongs to, the AdventureLog server version, and its capabilities.

        Call this first if anything else fails. Returns the username, display name, preferred units and
        currency, and how many collection invites are waiting.
        """
        a = api(ctx)
        account = await a.get("/api/account/")
        info = await a.get("/api/server-info/")
        user = account.get("user", {})
        return {
            "username": user.get("username"),
            "name": " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or None,
            "measurement_system": user.get("measurement_system"),
            "default_currency": user.get("default_currency"),
            "pending_collection_invites": account.get("pending_invite_count", 0),
            "server": {
                "url": info.get("public_url"),
                "version": info.get("version"),
                "capabilities": info.get("capabilities", []),
            },
        }
