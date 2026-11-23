import json

import httpx
import respx

from .conftest import BASE, data

C = f"{BASE}/api/collections/c1"
DAYS = [
    {"id": "d1", "index": 1, "date": "2027-06-03"},
    {"id": "d2", "index": 2, "date": "2027-06-04", "name": "Sintra"},
]
COLLECTION = {
    "id": "c1",
    "name": "Lisbon",
    "locations": [{"id": "l1", "name": "Castle"}, {"id": "l2", "name": "Market"}, {"id": "l3", "name": "Tower"}],
    "lodging": [{"id": "h1", "name": "Hotel"}],
    "notes": [{"id": "n1", "name": "Tips"}],
}


def item(iid, kind, obj, day=None, order=0, is_global=False, **extra):
    return {
        "id": iid,
        "content_type": kind,
        "object_id": obj,
        "day_index": day,
        "order": order,
        "is_global": is_global,
        **extra,
    }


def plan_state(items):
    return {
        "collection": {"id": "c1", "day_count": 2, "start_date": "2027-06-03"},
        "itinerary": items,
        "itinerary_days": DAYS,
    }


def mock_plan(items):
    respx.get(f"{C}/itinerary/").mock(return_value=httpx.Response(200, json=plan_state(items)))
    respx.get(f"{C}/").mock(return_value=httpx.Response(200, json=COLLECTION))


@respx.mock
async def test_get_day_plan_names_items_and_lists_what_is_not_scheduled(mcp):
    mock_plan(
        [
            item("i2", "location", "l2", day=1, order=1, start_time="13:00:00"),
            item("i1", "location", "l1", day=1, order=0, start_time="10:00:00"),
            item("i3", "lodging", "h1", day=1, order=2, span_end_index=2),
            item("i4", "location", "l3", order=0),
            item("i5", "note", "n1", is_global=True),
        ]
    )
    out = data(await mcp.tool("get_day_plan", {"collection_id": "c1"}))

    assert [(i["name"], i.get("start_time")) for i in out["days"][0]["items"]][:2] == [
        ("Castle", "10:00"),
        ("Market", "13:00"),
    ]  # ordered, named, "HH:MM"
    assert out["days"][0]["items"][2]["through_day"] == 2
    assert out["days"][1] == {"day": 2, "date": "2027-06-04", "name": "Sintra"}  # empty lists are left out
    assert out["ideas"][0]["name"] == "Tower" and out["trip_wide"][0]["name"] == "Tips"
    assert "not_scheduled_yet" not in out  # everything is placed


@respx.mock
async def test_unscheduled_records_are_reported(mcp):
    mock_plan([item("i1", "location", "l1", day=1)])
    out = data(await mcp.tool("get_day_plan", {"collection_id": "c1"}))
    assert {r["name"] for r in out["not_scheduled_yet"]["location"]} == {"Market", "Tower"}
    assert out["not_scheduled_yet"]["lodging"] == [{"id": "h1", "name": "Hotel"}]


@respx.mock
async def test_schedule_item_posts_a_new_placement(mcp):
    mock_plan([])
    post = respx.post(f"{C}/itinerary-items/").mock(return_value=httpx.Response(201, json={}))
    out = data(
        await mcp.tool(
            "schedule_item",
            {"collection_id": "c1", "kind": "location", "object_id": "l1", "day": 2, "start_time": "10:00"},
        )
    )
    assert json.loads(post.calls.last.request.content) == {
        "content_type": "location",
        "object_id": "l1",
        "start_time": "10:00",
        "day_index": 2,
    }
    assert "note" not in out


@respx.mock
async def test_schedule_item_repeat_changes_nothing(mcp):
    mock_plan([item("i1", "location", "l1", day=2)])
    post = respx.post(f"{C}/itinerary-items/").mock(return_value=httpx.Response(201, json={}))
    out = data(
        await mcp.tool("schedule_item", {"collection_id": "c1", "kind": "location", "object_id": "l1", "day": 2})
    )
    assert not post.called
    assert "nothing changed" in out["note"]


@respx.mock
async def test_schedule_item_moves_a_parked_item_instead_of_duplicating(mcp):
    mock_plan([item("ideas1", "location", "l1")])
    post = respx.post(f"{C}/itinerary-items/").mock(return_value=httpx.Response(201, json={}))
    patch = respx.patch(f"{C}/itinerary-items/ideas1/").mock(return_value=httpx.Response(200, json={}))
    out = data(
        await mcp.tool(
            "schedule_item", {"collection_id": "c1", "kind": "location", "object_id": "l1", "date": "2027-06-04"}
        )
    )
    assert not post.called
    assert json.loads(patch.calls.last.request.content) == {"day_index": 2, "is_global": False}  # date -> day 2
    assert out["note"] == "Moved from Ideas."


@respx.mock
async def test_schedule_item_rejects_a_date_outside_the_plan(mcp):
    mock_plan([])
    result = await mcp.tool(
        "schedule_item", {"collection_id": "c1", "kind": "location", "object_id": "l1", "date": "2030-01-01"}
    )
    assert result["isError"] and "not a day of this plan" in result["content"][0]["text"]


@respx.mock
async def test_order_day_items_keeps_left_out_items_after_the_listed_ones(mcp):
    mock_plan(
        [
            item("a", "location", "l1", day=1, order=0),
            item("b", "location", "l2", day=1, order=1),
            item("c", "note", "n1", day=1, order=2),
        ]
    )
    reorder = respx.post(f"{C}/itinerary/reorder/").mock(return_value=httpx.Response(200, json={"items": []}))

    await mcp.tool("order_day_items", {"collection_id": "c1", "day": 1, "item_ids": ["c"]})

    entries = json.loads(reorder.calls.last.request.content)["items"]
    assert [(e["id"], e["order"]) for e in entries] == [("c", 0), ("a", 1), ("b", 2)]
    assert all(e["day_index"] == 1 and e["is_global"] is False for e in entries)


@respx.mock
async def test_order_day_items_rejects_unknown_ids_before_touching_anything(mcp):
    mock_plan([item("a", "location", "l1", day=1)])
    reorder = respx.post(f"{C}/itinerary/reorder/").mock(return_value=httpx.Response(200, json={}))
    result = await mcp.tool("order_day_items", {"collection_id": "c1", "day": 1, "item_ids": ["zzz"]})
    assert result["isError"] and not reorder.called


@respx.mock
async def test_move_plan_item_to_ideas_and_set_day_details(mcp):
    mock_plan([item("a", "location", "l1", day=1)])
    patch = respx.patch(f"{C}/itinerary-items/a/").mock(return_value=httpx.Response(200, json={}))
    await mcp.tool("move_plan_item", {"collection_id": "c1", "item_id": "a", "to_ideas": True})
    assert json.loads(patch.calls.last.request.content) == {"day_index": None, "is_global": False}

    rename = respx.patch(f"{C}/days/d2/").mock(return_value=httpx.Response(200, json={}))
    await mcp.tool("set_day_details", {"collection_id": "c1", "day": 2, "name": "Sintra"})
    assert json.loads(rename.calls.last.request.content) == {"name": "Sintra"}

    bad = await mcp.tool("set_day_details", {"collection_id": "c1", "day": 9, "name": "x"})
    assert bad["isError"] and "no day 9" in bad["content"][0]["text"]


@respx.mock
async def test_shortening_without_a_destination_explains_what_to_choose(mcp):
    mock_plan([])
    respx.post(f"{C}/itinerary/duration/").mock(
        return_value=httpx.Response(400, json={"detail": "Choose where they go.", "code": "destination_required"})
    )
    result = await mcp.tool("set_plan_length", {"collection_id": "c1", "day_count": 1})
    assert result["isError"] and "destination_required" in result["content"][0]["text"]


@respx.mock
async def test_list_regions_merges_visited_state_and_filters(mcp):
    respx.get(f"{BASE}/api/countries/PT/regions/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": "PT-11", "name": "Lisbon", "num_cities": 287},
                {"id": "PT-13", "name": "Porto", "num_cities": 50},
            ],
        )
    )
    visited = respx.get(f"{BASE}/api/visited-regions/").mock(
        return_value=httpx.Response(200, json=[{"region": "PT-11"}])
    )
    out = data(await mcp.tool("list_regions", {"country_code": "pt"}))
    assert [(r["id"], r["visited"]) for r in out["regions"]] == [("PT-11", True), ("PT-13", False)]
    assert visited.calls.last.request.url.params["country"] == "PT"

    only = data(await mcp.tool("list_regions", {"country_code": "PT", "visited": False}))
    assert [r["id"] for r in only["regions"]] == ["PT-13"]


@respx.mock
async def test_list_countries_filters_the_reference_list(mcp):
    respx.get(f"{BASE}/api/countries/").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"country_code": "PT", "name": "Portugal", "num_regions": 20, "num_visits": 1},
                {"country_code": "ES", "name": "Spain", "num_regions": 19, "num_visits": 0},
            ],
        )
    )
    assert data(await mcp.tool("list_countries", {"query": "spai"}))["countries"][0]["code"] == "ES"
    visited = data(await mcp.tool("list_countries", {"visited_only": True}))
    assert [c["code"] for c in visited["countries"]] == ["PT"]


@respx.mock
async def test_mark_and_unmark_use_the_visited_endpoints(mcp):
    mark = respx.post(f"{BASE}/api/visited-regions/").mock(return_value=httpx.Response(201, json={"region": "PT-11"}))
    unmark = respx.delete(f"{BASE}/api/visited-cities/PT-11-1/").mock(return_value=httpx.Response(204))
    assert data(await mcp.tool("mark_region_visited", {"region_id": "PT-11"}))["visited"] is True
    assert json.loads(mark.calls.last.request.content) == {"region": "PT-11"}
    assert data(await mcp.tool("unmark_city_visited", {"city_id": "PT-11-1"}))["visited"] is False
    assert unmark.called


@respx.mock
async def test_travel_stats_are_summarised_for_the_signed_in_user(mcp):
    respx.get(f"{BASE}/api/account/").mock(return_value=httpx.Response(200, json={"user": {"username": "sean"}}))
    respx.get(f"{BASE}/api/users/sean/stats/").mock(
        return_value=httpx.Response(
            200,
            json={
                "location_count": 3, "visited_location_count": 1, "trips_count": 2, "visited_country_count": 1,
                "total_countries": 250, "visited_region_count": 4, "total_regions": 5348, "visited_city_count": 0,
                "total_cities": 152295, "activities_overall": {"big": "ignored"}, "activity_count": 0,
            },
        )
    )  # fmt: skip
    out = data(await mcp.tool("get_travel_stats"))
    assert out["countries"] == {"visited": 1, "total": 250} and out["collections"] == 2
    assert "activities_overall" not in out
