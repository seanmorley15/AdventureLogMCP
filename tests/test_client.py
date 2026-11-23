import httpx
import respx

from adventurelog_mcp.client import AdventureLogClient
from adventurelog_mcp.config import Settings

from .conftest import BASE, KEY


@respx.mock
async def test_follows_the_frontends_308_and_keeps_method_body_and_key():
    respx.post(f"{BASE}/api/collections/").mock(
        return_value=httpx.Response(308, headers={"location": "../collections"})
    )
    final = respx.post(f"{BASE}/api/collections").mock(return_value=httpx.Response(201, json={"id": "x"}))
    client = AdventureLogClient(Settings(adventurelog_url=BASE))

    out = await client.post("/api/collections/", api_key=KEY, json={"name": "Lisbon"})

    assert out == {"id": "x"}
    sent = final.calls.last.request
    assert sent.headers["x-api-key"] == KEY and b"Lisbon" in sent.content
