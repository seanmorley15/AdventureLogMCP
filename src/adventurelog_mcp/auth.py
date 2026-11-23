"""Find the caller's AdventureLog API key.

HTTP clients send it on the MCP request (``Authorization: Bearer al_...``, ``Authorization: Api-Key al_...``
or ``X-API-Key``); it is forwarded to AdventureLog unchanged, so the server stores nothing and every
caller acts as themselves. stdio and single-user setups fall back to ``ADVENTURELOG_API_KEY``.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from .client import AdventureLogClient, AdventureLogError, stable_id
from .config import get_settings

MISSING_KEY = (
    "No AdventureLog API key was sent. Create one in AdventureLog under Settings > Security > API Keys and "
    "send it as 'Authorization: Bearer al_...' (or 'X-API-Key: al_...')."
)


def key_from_headers(headers: Any) -> str | None:
    """Pull the key out of a mapping of request headers (case-insensitive, like Starlette's)."""
    x_key = headers.get("x-api-key")
    if x_key and x_key.strip():
        return x_key.strip()
    auth = headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() in {"bearer", "api-key"} and token.strip():
        return token.strip()
    return None


def api_key_for(ctx: Context) -> str:
    request = getattr(ctx.request_context, "request", None)
    if request is not None:
        key = key_from_headers(request.headers)
        if key:
            return key
    fallback = get_settings().adventurelog_api_key
    if fallback:
        return fallback
    raise ToolError(MISSING_KEY)


class Api:
    """The shared client bound to one caller's key. Turns API errors into messages for the model."""

    def __init__(self, client: AdventureLogClient, api_key: str):
        self._client = client
        self._key = api_key

    def create_body(self, kind: str, **fields: Any) -> dict[str, Any]:
        """A create request body: the non-None fields plus an `id` that makes repeating the call safe."""
        body = {k: v for k, v in fields.items() if v is not None}
        return {"id": stable_id(self._key, kind, body), **body}

    async def request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            return await self._client.request(method, path, api_key=self._key, **kw)
        except AdventureLogError as e:
            raise ToolError(e.for_model()) from e

    async def get(self, path: str, **kw: Any) -> Any:
        return await self.request("GET", path, **kw)

    async def post(self, path: str, **kw: Any) -> Any:
        return await self.request("POST", path, **kw)

    async def patch(self, path: str, **kw: Any) -> Any:
        return await self.request("PATCH", path, **kw)

    async def delete(self, path: str, **kw: Any) -> Any:
        return await self.request("DELETE", path, **kw)


_client: AdventureLogClient | None = None


def shared_client() -> AdventureLogClient:
    global _client
    if _client is None:
        _client = AdventureLogClient()
    return _client


def set_shared_client(client: AdventureLogClient | None) -> None:
    """Swap the process-wide client (tests)."""
    global _client
    _client = client


def api(ctx: Context) -> Api:
    return Api(shared_client(), api_key_for(ctx))
