import httpx
import respx

from .conftest import BASE, KEY, data

ACCOUNT = {
    "user": {
        "username": "sean",
        "first_name": "Sean",
        "last_name": "Morley",
        "measurement_system": "metric",
        "default_currency": "USD",
    },
    "pending_invite_count": 2,
}
INFO = {"public_url": "https://adv.example.com", "version": "v0.14.0", "capabilities": ["client_ids_v1"]}


@respx.mock
async def test_whoami_forwards_the_callers_key(mcp):
    account = respx.get(f"{BASE}/api/account/").mock(return_value=httpx.Response(200, json=ACCOUNT))
    respx.get(f"{BASE}/api/server-info/").mock(return_value=httpx.Response(200, json=INFO))

    result = await mcp.tool("whoami")

    body = data(result)
    assert body["username"] == "sean"
    assert body["server"]["version"] == "v0.14.0"
    sent = account.calls.last.request.headers
    assert sent["x-api-key"] == KEY
    assert sent["origin"] == BASE


@respx.mock
async def test_x_api_key_header_also_works(mcp):
    account = respx.get(f"{BASE}/api/account/").mock(return_value=httpx.Response(200, json=ACCOUNT))
    respx.get(f"{BASE}/api/server-info/").mock(return_value=httpx.Response(200, json=INFO))

    await mcp.tool("whoami", key=None, headers={"X-API-Key": "al_other"})

    assert account.calls.last.request.headers["x-api-key"] == "al_other"


async def test_missing_key_is_a_tool_error_that_says_how_to_fix_it(mcp):
    result = await mcp.tool("whoami", key=None)
    assert result["isError"] is True
    assert "Settings > Security" in result["content"][0]["text"]


@respx.mock
async def test_adventurelog_error_envelope_reaches_the_model(mcp):
    respx.get(f"{BASE}/api/account/").mock(
        return_value=httpx.Response(
            401, json={"detail": "Invalid or expired API key.", "code": "authentication_failed"}
        )
    )
    result = await mcp.tool("whoami")
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "Invalid or expired API key" in text and "authentication_failed" in text


@respx.mock
async def test_unreachable_server_is_reported_not_crashed(mcp):
    respx.get(f"{BASE}/api/account/").mock(side_effect=httpx.ConnectError("boom"))
    result = await mcp.tool("whoami")
    assert result["isError"] is True
    assert "Could not reach AdventureLog" in result["content"][0]["text"]


async def test_health(mcp):
    resp = await mcp.http.get("/health")
    assert resp.status_code == 200 and resp.json()["status"] == "ok"
