"""The failing case from a real session: save a place with a NEW category, your own description and photos."""

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _live import live  # noqa: E402


async def main() -> int:
    async with live() as t:
        col = await t.call(
            "create_collection",
            name="MCP save-place check",
            type="plan",
            start_date="2027-05-13",
            end_date="2027-05-17",
            show=0,
        )
        t.cleanup.append(f"/api/collections/{col['id']}/")
        found = await t.call("search_places", query="Seneca Rocks West Virginia", limit=1, show=300)
        place = found["results"][0]
        t.check("search_places returns photo addresses", bool(place.get("photos")))
        mine = "Morning hike: Seneca Rocks Trail to the platform. (my own words)"
        loc = await t.call(
            "save_place_as_location", name=place["name"], latitude=place["latitude"], longitude=place["longitude"],
            place_id=place["place_id"], address=place["address"], category="hiking_area", description=mine,
            collection_id=col["id"], itinerary_date="2027-05-16", show=500,
        )  # fmt: skip
        t.cleanup.append(f"/api/locations/{loc['id']}/")
        t.check("new category was created, shown nicely", loc.get("category") == "Hiking Area")
        t.check("my description was kept", loc.get("description") == mine)
        t.check("photos were imported", loc.get("image_count", 0) >= 1 and not loc.get("photos_failed"))
        cats = await t.call("list_categories", show=200)
        t.check("category now listed", any(c["name"] == "hiking area" for c in cats["categories"]))
        again = await t.call(
            "create_location", name="Other spot", latitude=38.8, longitude=-79.3, category="Hiking Area", show=0
        )
        t.cleanup.append(f"/api/locations/{again['id']}/")
        t.check("same category reused by name", again.get("category") == "Hiking Area")
    return 1 if t.errors else 0


sys.exit(asyncio.run(main()))
