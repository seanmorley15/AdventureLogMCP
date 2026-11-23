"""Pictures: find, attach (place photo + a web picture), list, set the cover."""

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _live import live  # noqa: E402


async def main() -> int:
    async with live() as t:
        loc = await t.call("create_location", name="MCP media check", latitude=38.83, longitude=-79.37, show=0)
        t.cleanup.append(f"/api/locations/{loc['id']}/")
        found = await t.call("find_images", query="Seneca Rocks", show=300)
        t.check("find_images returns pictures", bool(found["images"]))
        place = (await t.call("search_places", query="Seneca Rocks West Virginia", limit=1, show=0))["results"][0]
        added = await t.call(
            "add_images", kind="location", record_id=loc["id"], urls=place["photos"][:2] + [found["images"][0]["url"]],
            show=600,
        )  # fmt: skip
        t.check("at least one picture added", (added.get("added") or 0) >= 1)
        listed = await t.call("list_images", kind="location", record_id=loc["id"], show=400)
        t.check("pictures listed with a cover", any(i.get("is_primary") for i in listed["images"]))
        if len(listed["images"]) > 1:
            other = next(i for i in listed["images"] if not i.get("is_primary"))
            res = await t.call("set_primary_image", image_id=other["id"], show=200)
            t.check("cover changed", res.get("is_primary") is True)
        full = await t.call("get_location", location_id=loc["id"], show=0)
        t.check("get_location shows images", full.get("image_count", 0) >= 1)
    return 1 if t.errors else 0


sys.exit(asyncio.run(main()))
