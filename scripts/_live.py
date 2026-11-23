"""Shared helper for the live smoke scripts: call MCP tools in-process against a real AdventureLog (.env)."""

import json
import logging
from contextlib import asynccontextmanager

import httpx

from adventurelog_mcp.client import AdventureLogClient, AdventureLogError
from adventurelog_mcp.config import get_settings
from adventurelog_mcp.server import build_http_app

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class Live:
    def __init__(self, http, key):
        self.http, self.key, self.n, self.errors, self.cleanup = http, key, 0, 0, []

    async def call(self, tool: str, /, show: int = 240, expect_error: bool = False, **args):
        self.n += 1
        body = {"jsonrpc": "2.0", "id": self.n, "method": "tools/call", "params": {"name": tool, "arguments": args}}
        r = await self.http.post("/mcp", json=body, headers={**HEADERS, "X-API-Key": self.key})
        res = json.loads(r.text)["result"]
        text = res["content"][0]["text"] if res["content"] else ""
        ok = not res.get("isError")
        self.errors += (ok == expect_error) if expect_error else (not ok)
        label = "OK " if ok else ("ERR (expected)" if expect_error else "ERR")
        print(f"\n{label} {tool}({', '.join(f'{k}={v!r}'[:34] for k, v in args.items())})")
        if show:
            print("   " + " ".join(text.split())[:show])
        return json.loads(text) if ok else text

    def check(self, label: str, cond: bool):
        print(f"   CHECK {'pass' if cond else 'FAIL'}: {label}")
        self.errors += not cond


@asynccontextmanager
async def live():
    """A Live session; everything appended to `.cleanup` as an API path is deleted afterwards."""
    logging.disable(logging.INFO)
    s = get_settings()
    app = build_http_app()
    session = None
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as http:
                session = Live(http, s.adventurelog_api_key)
                yield session
    finally:
        client = AdventureLogClient()
        for path in reversed(session.cleanup if session else []):
            try:
                await client.delete(path, api_key=s.adventurelog_api_key)
            except AdventureLogError:
                pass
        left = [
            (await client.get(p, api_key=s.adventurelog_api_key))["count"]
            for p in ("/api/collections/", "/api/locations/")
        ]
        await client.aclose()
        print(f"\nleft behind: {left[0]} collections, {left[1]} locations")
