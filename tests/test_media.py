import json

import httpx
import respx

from .conftest import BASE, data


@respx.mock
async def test_find_images_returns_urls(mcp):
    respx.get(f"{BASE}/api/places/images/").mock(
        return_value=httpx.Response(200, json={"images": [{"source": "https://x/a.jpg", "title": "A", "width": 9}]})
    )
    out = data(await mcp.tool("find_images", {"query": "Seneca Rocks"}))
    assert out["images"][0]["url"] == "https://x/a.jpg"


@respx.mock
async def test_add_images_reports_each_address_and_marks_google_photos(mcp):
    route = respx.post(f"{BASE}/api/images/import-from-urls/").mock(
        return_value=httpx.Response(
            200,
            json={
                "created": [{"id": "i1", "image": "http://m/i1.webp", "is_primary": True, "source": "google"}],
                "results": [
                    {"url": "/api/places/photo/?name=a", "status": "created"},
                    {"url": "/api/places/photo/?name=b", "status": "failed", "error": "nope"},
                ],
                "created_count": 1,
                "requested_count": 2,
            },
        )
    )
    out = data(
        await mcp.tool(
            "add_images",
            {"kind": "location", "record_id": "l1", "urls": ["/api/places/photo/?name=a", "/api/places/photo/?name=b"]},
        )
    )
    assert json.loads(route.calls.last.request.content)["source"] == "google"
    assert out["added"] == 1 and out["requested"] == 2
    assert out["results"][1]["error"] == "nope"


@respx.mock
async def test_set_primary_treats_already_primary_as_done(mcp):
    respx.post(f"{BASE}/api/images/i1/toggle-primary/").mock(
        return_value=httpx.Response(
            400, json={"detail": "This image is already the primary image.", "code": "already_primary"}
        )
    )
    out = data(await mcp.tool("set_primary_image", {"image_id": "i1"}))
    assert out["is_primary"] is True


@respx.mock
async def test_get_location_shows_images(mcp):
    respx.get(f"{BASE}/api/locations/l1/").mock(
        return_value=httpx.Response(
            200,
            json={"id": "l1", "name": "X", "images": [{"id": "i1", "image": "http://m/i1.webp", "is_primary": True}]},
        )
    )
    out = data(await mcp.tool("get_location", {"location_id": "l1"}))
    assert out["image_count"] == 1 and out["images"][0]["is_primary"]


@respx.mock
async def test_save_place_finds_photos_itself_when_none_given(mcp):
    respx.post(f"{BASE}/api/locations/check-duplicates/").mock(return_value=httpx.Response(200, json={"matches": []}))
    respx.get(f"{BASE}/api/places/search/").mock(
        return_value=httpx.Response(
            200, json={"results": [{"place_id": "p1", "photos": ["/api/places/photo/?name=a"]}]}
        )
    )
    route = respx.post(f"{BASE}/api/locations/quick-add/").mock(
        return_value=httpx.Response(201, json={"id": "l1", "name": "X"})
    )
    await mcp.tool("save_place_as_location", {"name": "X", "latitude": 1, "longitude": 2, "place_id": "p1"})
    assert json.loads(route.calls.last.request.content)["photos"] == ["/api/places/photo/?name=a"]


@respx.mock
async def test_save_place_still_saves_when_photo_lookup_fails(mcp):
    respx.post(f"{BASE}/api/locations/check-duplicates/").mock(return_value=httpx.Response(200, json={"matches": []}))
    respx.get(f"{BASE}/api/places/search/").mock(return_value=httpx.Response(500, text="boom"))
    route = respx.post(f"{BASE}/api/locations/quick-add/").mock(
        return_value=httpx.Response(201, json={"id": "l1", "name": "X"})
    )
    await mcp.tool("save_place_as_location", {"name": "X", "latitude": 1, "longitude": 2, "place_id": "p1"})
    assert "photos" not in json.loads(route.calls.last.request.content)


@respx.mock
async def test_create_location_reuses_a_matching_existing_category(mcp):
    respx.post(f"{BASE}/api/locations/check-duplicates/").mock(return_value=httpx.Response(200, json={"matches": []}))
    respx.get(f"{BASE}/api/categories/").mock(
        return_value=httpx.Response(200, json=[{"name": "hiking area", "display_name": "Hiking Area"}])
    )
    route = respx.post(f"{BASE}/api/locations/").mock(return_value=httpx.Response(201, json={"id": "l1", "name": "X"}))
    await mcp.tool("create_location", {"name": "X", "latitude": 1, "longitude": 2, "category": "hiking_areas"})
    assert json.loads(route.calls.last.request.content)["category"] == {
        "name": "hiking area",
        "display_name": "Hiking Area",
    }


@respx.mock
async def test_create_location_makes_a_new_category_when_none_fits(mcp):
    respx.post(f"{BASE}/api/locations/check-duplicates/").mock(return_value=httpx.Response(200, json={"matches": []}))
    respx.get(f"{BASE}/api/categories/").mock(
        return_value=httpx.Response(200, json=[{"name": "museum", "display_name": "Museum"}])
    )
    route = respx.post(f"{BASE}/api/locations/").mock(return_value=httpx.Response(201, json={"id": "l1", "name": "X"}))
    await mcp.tool("create_location", {"name": "X", "latitude": 1, "longitude": 2, "category": "waterfall"})
    assert json.loads(route.calls.last.request.content)["category"]["display_name"] == "Waterfall"


@respx.mock
async def test_a_plan_can_be_made_by_day_count_alone(mcp):
    route = respx.post(f"{BASE}/api/collections/").mock(
        return_value=httpx.Response(201, json={"id": "c1", "name": "Iceland", "type": "trip", "day_count": 5})
    )
    await mcp.tool("create_collection", {"name": "Iceland", "type": "plan", "day_count": 5})
    body = json.loads(route.calls.last.request.content)
    assert body["type"] == "trip" and body["day_count"] == 5 and "start_date" not in body


@respx.mock
async def test_create_location_reuses_a_saved_place_and_adds_it_to_the_collection(mcp):
    respx.post(f"{BASE}/api/locations/check-duplicates/").mock(
        return_value=httpx.Response(
            200, json={"matches": [{"id": "old1", "name": "Seneca Rocks", "score": 0.97, "reasons": ["similar_name"]}]}
        )
    )
    link = respx.post(f"{BASE}/api/locations/old1/collections/c1/").mock(
        return_value=httpx.Response(200, json={"linked": True})
    )
    respx.get(f"{BASE}/api/locations/old1/").mock(
        return_value=httpx.Response(200, json={"id": "old1", "name": "Seneca Rocks"})
    )
    create = respx.post(f"{BASE}/api/locations/")
    out = data(
        await mcp.tool(
            "create_location", {"name": "Seneca Rocks", "latitude": 1, "longitude": 2, "collection_id": "c1"}
        )
    )
    assert out["reused_existing"] is True and out["id"] == "old1"
    assert link.called and not create.called


@respx.mock
async def test_a_merely_nearby_place_is_not_reused(mcp):
    respx.post(f"{BASE}/api/locations/check-duplicates/").mock(
        return_value=httpx.Response(
            200, json={"matches": [{"id": "n1", "name": "Other", "score": 0.97, "reasons": ["nearby_coordinates"]}]}
        )
    )
    create = respx.post(f"{BASE}/api/locations/").mock(
        return_value=httpx.Response(201, json={"id": "new", "name": "X"})
    )
    out = data(await mcp.tool("create_location", {"name": "X", "latitude": 1, "longitude": 2}))
    assert create.called and not out.get("reused_existing")
