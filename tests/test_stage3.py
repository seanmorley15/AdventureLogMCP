import json

import httpx
import respx

from .conftest import BASE, data

LOC = {"id": "l1", "name": "Edited", "category": {"display_name": "Nature"}, "latitude": 1, "longitude": 2}


def body_of(route) -> dict:
    return json.loads(route.calls.last.request.content)


async def tool_names(caller) -> set[str]:
    resp = await caller.rpc("tools/list")
    return {t["name"] for t in json.loads(resp.text)["result"]["tools"]}


# --- safety: deletes are opt-in ---------------------------------------------------------------------------

DELETE_TOOLS = {
    "delete_location", "delete_collection", "delete_lodging", "delete_transportation", "delete_note",
    "delete_checklist", "delete_visit",
}  # fmt: skip


async def test_delete_tools_do_not_exist_by_default(mcp):
    names = await tool_names(mcp)
    assert not (names & DELETE_TOOLS)
    assert {"update_location", "remove_plan_item"} <= names  # edits and unscheduling are always there


async def test_delete_tools_appear_only_when_enabled(mcp_destructive):
    names = await tool_names(mcp_destructive)
    assert DELETE_TOOLS <= names
    tools = json.loads((await mcp_destructive.rpc("tools/list")).text)["result"]["tools"]
    assert all(t["annotations"]["destructiveHint"] for t in tools if t["name"] in DELETE_TOOLS)


@respx.mock
async def test_delete_calls_the_right_endpoint(mcp_destructive):
    route = respx.delete(f"{BASE}/api/collections/c1/").mock(return_value=httpx.Response(204))
    out = data(await mcp_destructive.tool("delete_collection", {"collection_id": "c1"}))
    assert route.called and out == {"deleted": True, "kind": "collection", "id": "c1"}


@respx.mock
async def test_deleting_something_already_gone_is_an_error_the_model_can_read(mcp_destructive):
    respx.delete(f"{BASE}/api/notes/n1/").mock(
        return_value=httpx.Response(404, json={"detail": "Not found.", "code": "not_found"})
    )
    result = await mcp_destructive.tool("delete_note", {"note_id": "n1"})
    assert result["isError"] and "not_found" in result["content"][0]["text"]


# --- edits --------------------------------------------------------------------------------------------------


@respx.mock
async def test_update_location_sends_only_changed_fields_and_the_category_object(mcp):
    route = respx.patch(f"{BASE}/api/locations/l1/").mock(
        return_value=httpx.Response(200, json=LOC, headers={"ETag": '"2"'})
    )
    out = data(await mcp.tool("update_location", {"location_id": "l1", "name": "Edited", "category": " Nature "}))
    assert body_of(route) == {"name": "Edited", "category": {"name": "nature", "display_name": "Nature"}}
    assert "if-match" not in route.calls.last.request.headers
    assert out["version"] == '"2"' and out["category"] == "Nature"


@respx.mock
async def test_update_with_a_version_sends_if_match(mcp):
    route = respx.patch(f"{BASE}/api/locations/l1/").mock(return_value=httpx.Response(200, json=LOC))
    await mcp.tool("update_location", {"location_id": "l1", "rating": 4, "version": '"1"'})
    assert route.calls.last.request.headers["if-match"] == '"1"'


@respx.mock
async def test_a_stale_version_saves_nothing_and_returns_the_current_record(mcp):
    respx.patch(f"{BASE}/api/locations/l1/").mock(
        return_value=httpx.Response(
            412,
            json={"detail": "Changed.", "code": "precondition_failed", "current": LOC},
            headers={"ETag": '"9"'},
        )
    )
    result = await mcp.tool("update_location", {"location_id": "l1", "name": "Mine", "version": '"1"'})
    text = result["content"][0]["text"]
    assert result["isError"] is True
    assert "precondition_failed" in text and '"name": "Edited"' in text and '"9"' in text
    assert "images" not in text  # the current record is shown in the short form


async def test_an_edit_with_nothing_to_change_is_refused(mcp):
    result = await mcp.tool("update_note", {"note_id": "n1"})
    assert result["isError"] and "Nothing to change" in result["content"][0]["text"]


@respx.mock
async def test_update_collection_maps_plan_to_trip_and_has_no_end_date(mcp):
    route = respx.patch(f"{BASE}/api/collections/c1/").mock(
        return_value=httpx.Response(200, json={"id": "c1", "name": "L", "type": "trip"})
    )
    out = data(await mcp.tool("update_collection", {"collection_id": "c1", "type": "plan", "start_date": "2027-07-01"}))
    assert body_of(route) == {"type": "trip", "start_date": "2027-07-01"}
    assert out["type"] == "plan"
    tools = json.loads((await mcp.rpc("tools/list")).text)["result"]["tools"]
    schema = next(t for t in tools if t["name"] == "update_collection")["inputSchema"]["properties"]
    assert "end_date" not in schema  # it follows from start date and length


@respx.mock
async def test_update_checklist_replaces_the_items(mcp):
    route = respx.patch(f"{BASE}/api/checklists/k1/").mock(
        return_value=httpx.Response(
            200, json={"id": "k1", "name": "Pack", "items": [{"name": "A", "is_checked": True}]}
        )
    )
    out = data(await mcp.tool("update_checklist", {"checklist_id": "k1", "items": [{"name": "A", "is_checked": True}]}))
    assert body_of(route) == {"items": [{"name": "A", "is_checked": True}]}
    assert out["items"][0]["is_checked"] is True


@respx.mock
async def test_remove_plan_item_unschedules_and_returns_the_plan(mcp):
    delete = respx.delete(f"{BASE}/api/collections/c1/itinerary-items/i1/").mock(return_value=httpx.Response(204))
    respx.get(f"{BASE}/api/collections/c1/itinerary/").mock(
        return_value=httpx.Response(200, json={"collection": {}, "itinerary": [], "itinerary_days": []})
    )
    respx.get(f"{BASE}/api/collections/c1/").mock(
        return_value=httpx.Response(200, json={"id": "c1", "name": "L", "locations": [{"id": "l1", "name": "Castle"}]})
    )
    out = data(await mcp.tool("remove_plan_item", {"collection_id": "c1", "item_id": "i1"}))
    assert delete.called
    assert out["not_scheduled_yet"]["location"] == [{"id": "l1", "name": "Castle"}]


# --- reads expose the version -----------------------------------------------------------------------------


@respx.mock
async def test_get_location_and_create_collection_return_a_version(mcp):
    respx.get(f"{BASE}/api/locations/l1/").mock(return_value=httpx.Response(200, json=LOC, headers={"ETag": '"5"'}))
    respx.post(f"{BASE}/api/collections/").mock(
        return_value=httpx.Response(201, json={"id": "c1", "name": "L"}, headers={"ETag": '"6"'})
    )
    assert data(await mcp.tool("get_location", {"location_id": "l1"}))["version"] == '"5"'
    assert data(await mcp.tool("create_collection", {"name": "L"}))["version"] == '"6"'


# --- prompts ------------------------------------------------------------------------------------------------


async def test_prompts_list_and_render(mcp):
    listed = json.loads((await mcp.rpc("prompts/list")).text)["result"]["prompts"]
    assert {p["name"] for p in listed} == {"plan_collection", "collection_briefing", "year_in_review"}

    resp = await mcp.rpc(
        "prompts/get", {"name": "plan_collection", "arguments": {"destination": "Lisbon", "dates": "June 3-6"}}
    )
    text = json.loads(resp.text)["result"]["messages"][0]["content"]["text"]
    assert "Lisbon" in text and "June 3-6" in text and "trip" not in text.lower().replace("plan-wide", "")
