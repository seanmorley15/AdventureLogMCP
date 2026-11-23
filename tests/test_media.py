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
