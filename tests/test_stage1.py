import json

import httpx
import respx

from adventurelog_mcp.client import stable_id

from .conftest import BASE, data


def sent(route) -> dict:
    return json.loads(route.calls.last.request.content)


def test_stable_id_is_repeatable_per_caller_and_request():
    a = stable_id("al_one", "location", {"name": "X"})
    assert a == stable_id("al_one", "location", {"name": "X"})
    assert a != stable_id("al_two", "location", {"name": "X"})  # another user never collides
    assert a != stable_id("al_one", "location", {"name": "Y"})
    assert a != stable_id("al_one", "note", {"name": "X"})


@respx.mock
async def test_create_collection_maps_plan_to_trip_and_repeats_with_the_same_id(mcp):
    route = respx.post(f"{BASE}/api/collections/").mock(
        return_value=httpx.Response(
            201, json={"id": "c1", "name": "Lisbon", "type": "trip", "start_date": "2027-06-03"}
        )
    )
    args = {"name": "Lisbon", "type": "plan", "start_date": "2027-06-03", "end_date": "2027-06-06"}

    out = data(await mcp.tool("create_collection", args))
    await mcp.tool("create_collection", args)

    assert out["type"] == "plan"  # never "trip" towards the model
    first, second = (json.loads(c.request.content) for c in route.calls)
    assert first["type"] == "trip" and first["id"] == second["id"]


@respx.mock
async def test_create_location_sends_category_as_object_and_collection_list(mcp):
    route = respx.post(f"{BASE}/api/locations/").mock(
        return_value=httpx.Response(201, json={"id": "l1", "name": "Viewpoint", "category": {"display_name": "Nature"}})
    )

    out = data(
        await mcp.tool(
            "create_location",
            {
                "name": "Viewpoint",
                "latitude": 38.7,
                "longitude": -9.1,
                "category": " Nature ",
                "collection_id": "c1",
                "visits": [{"start_date": "2027-06-04", "notes": "Sunset"}],
            },
        )
    )

    body = sent(route)
    assert body["category"] == {"name": "nature", "display_name": "Nature"}
    assert body["collections"] == ["c1"]
    assert body["visits"] == [{"start_date": "2027-06-04", "notes": "Sunset"}]
    assert "rating" not in body and "link" not in body  # unset fields are not sent
    assert out["category"] == "Nature"


@respx.mock
async def test_validation_errors_tell_the_model_which_field_to_fix(mcp):
    respx.post(f"{BASE}/api/collections/").mock(
        return_value=httpx.Response(
            400,
            json={
                "detail": "end_date: before start",
                "code": "validation_error",
                "fields": {"end_date": ["Must be after start."]},
            },
        )
    )
    result = await mcp.tool(
        "create_collection", {"name": "X", "type": "plan", "start_date": "2027-06-05", "end_date": "2027-06-01"}
    )
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "validation_error" in text and "end_date: Must be after start." in text


@respx.mock
async def test_search_reshapes_the_api_hits(mcp):
    respx.get(f"{BASE}/api/search/").mock(
        return_value=httpx.Response(
            200,
            json={
                "count": 1,
                "results": [
                    {"type": "collection", "id": "c1", "title": "Lisbon", "subtitle": "", "url": "/x", "score": 1}
                ],
                "facets": {"collection": 1, "note": 0},
            },
        )
    )
    out = data(await mcp.tool("search", {"query": "Lisbon"}))
    assert out["results"] == [{"type": "collection", "id": "c1", "name": "Lisbon"}]
    assert out["matches_by_kind"] == {"collection": 1}


@respx.mock
async def test_get_collection_returns_everything_inside_in_short_form(mcp):
    respx.get(f"{BASE}/api/collections/c1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "c1", "name": "Lisbon", "type": "trip", "user": "u",
                "locations": [{"id": "l1", "name": "Castle", "images": [1, 2]}],
                "lodging": [{"id": "h1", "name": "Hotel", "type": "hotel", "check_in": "2027-06-03T15:00:00Z"}],
                "transportations": [
                    {"id": "t1", "name": "TP204", "type": "plane", "from_location": "JFK", "to_location": "LIS"}
                ],
                "notes": [{"id": "n1", "name": "Tips", "content": "Tram 28"}],
                "checklists": [{"id": "k1", "name": "Packing", "items": [{"name": "Passport", "is_checked": True}]}],
            },
        )
    )  # fmt: skip
    out = data(await mcp.tool("get_collection", {"collection_id": "c1"}))
    assert out["type"] == "plan"
    assert out["locations"] == [{"id": "l1", "name": "Castle"}]
    assert out["lodgings"][0]["check_in"] == "2027-06-03T15:00:00Z"
    assert out["transportations"][0]["from"] == "JFK"
    assert out["notes"][0]["content"] == "Tram 28"
    assert out["checklists"][0]["items"] == [{"name": "Passport", "is_checked": True}]
    assert "user" not in out


@respx.mock
async def test_collection_items_are_created_inside_the_collection(mcp):
    for path in ("lodgings", "transportations", "notes", "checklists"):
        respx.post(f"{BASE}/api/{path}/").mock(
            return_value=httpx.Response(201, json={"id": "x", "name": "n", "items": []})
        )

    await mcp.tool("create_lodging", {"name": "Hotel", "collection_id": "c1", "type": "hotel"})
    await mcp.tool(
        "create_transportation", {"name": "TP204", "type": "plane", "collection_id": "c1", "start_code": "JFK"}
    )
    await mcp.tool("create_note", {"name": "Tips", "content": "Tram", "collection_id": "c1"})
    await mcp.tool("create_checklist", {"name": "Packing", "collection_id": "c1", "items": [{"name": "Passport"}]})

    calls = [json.loads(c.request.content) for c in respx.calls]
    assert [c["collection"] for c in calls] == ["c1"] * 4
    assert calls[1]["start_code"] == "JFK" and calls[3]["items"][0]["name"] == "Passport"


@respx.mock
async def test_location_membership_tools_use_the_link_endpoint(mcp):
    respx.post(f"{BASE}/api/locations/l1/collections/c1/").mock(return_value=httpx.Response(200, json={"linked": True}))
    respx.delete(f"{BASE}/api/locations/l1/collections/c1/").mock(
        return_value=httpx.Response(200, json={"linked": False, "removed_placements": 2})
    )
    assert data(await mcp.tool("add_location_to_collection", {"location_id": "l1", "collection_id": "c1"})) == {
        "linked": True
    }
    out = data(await mcp.tool("remove_location_from_collection", {"location_id": "l1", "collection_id": "c1"}))
    assert out == {"linked": False, "removed_day_plan_entries": 2}


async def test_every_tool_declares_whether_it_changes_data(mcp):
    resp = await mcp.rpc("tools/list")
    tools = json.loads(resp.text)["result"]["tools"]
    assert len(tools) >= 21
    for t in tools:
        assert "readOnlyHint" in t["annotations"], t["name"]
