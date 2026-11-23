from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from adventurelog_mcp import auth
from adventurelog_mcp.client import AdventureLogClient
from adventurelog_mcp.config import Settings, get_settings
from adventurelog_mcp.server import build_http_app

BASE = "http://adventurelog.test"
KEY = "al_testkey123"
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("ADVENTURELOG_URL", BASE)
    monkeypatch.setenv("ADVENTURELOG_API_KEY", "")
    get_settings.cache_clear()
    auth.set_shared_client(AdventureLogClient(Settings(adventurelog_url=BASE)))
    yield
    auth.set_shared_client(None)
    get_settings.cache_clear()


def data(result: dict):
    """The JSON a tool returned (tools answer with one JSON text block)."""
    assert not result.get("isError"), result
    return json.loads(result["content"][0]["text"])


class McpCaller:
    """Speaks JSON-RPC to the real HTTP app, in process."""

    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self._id = 0

    async def rpc(self, method: str, params: dict | None = None, headers: dict | None = None):
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        resp = await self.http.post("/mcp", json=body, headers={**HEADERS, **(headers or {})})
        return resp

    async def tool(self, name: str, arguments: dict | None = None, key: str | None = KEY, headers: dict | None = None):
        h = dict(headers or {})
        if key:
            h.setdefault("Authorization", f"Bearer {key}")
        resp = await self.rpc("tools/call", {"name": name, "arguments": arguments or {}}, h)
        assert resp.status_code == 200, resp.text
        return json.loads(resp.text)["result"]


async def _serve():
    app = build_http_app()
    started, stop = asyncio.Event(), asyncio.Event()

    async def run_lifespan():
        # anyio cancel scopes must be entered and exited by the same task, so the app's lifespan gets its own.
        async with app.router.lifespan_context(app):
            started.set()
            await stop.wait()

    task = asyncio.create_task(run_lifespan())
    await started.wait()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://mcp.test") as http:
            yield McpCaller(http)
    finally:
        stop.set()
        await task


@pytest.fixture
async def mcp():
    async for caller in _serve():
        yield caller


@pytest.fixture
async def mcp_destructive(monkeypatch):
    """The server as started with MCP_ALLOW_DESTRUCTIVE=true."""
    monkeypatch.setenv("MCP_ALLOW_DESTRUCTIVE", "true")
    get_settings.cache_clear()
    async for caller in _serve():
        yield caller
