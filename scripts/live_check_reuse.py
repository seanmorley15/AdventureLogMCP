"""Saving a place the user already has reuses it, and adds it to the new collection."""

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _live import live  # noqa: E402


async def main() -> int:
    async with live() as t:
        first = await t.call("create_location", name="Seneca Rocks", latitude=38.8348, longitude=-79.3762, show=0)
        t.cleanup.append(f"/api/locations/{first['id']}/")
        col = await t.call("create_collection", name="MCP reuse check", show=0)
        t.cleanup.append(f"/api/collections/{col['id']}/")
        again = await t.call(
            "create_location", name="Seneca Rocks", latitude=38.8349, longitude=-79.3761, collection_id=col["id"],
            show=300,
        )  # fmt: skip
        t.check("same location reused", again["id"] == first["id"] and again.get("reused_existing"))
        t.check("added to the collection", col["id"] in (again.get("collection_ids") or []))
        other = await t.call(
            "create_location", name="Totally Different Cafe", latitude=38.8349, longitude=-79.3761, show=0
        )
        t.cleanup.append(f"/api/locations/{other['id']}/")
        t.check("a different place nearby is kept separate", other["id"] != first["id"])
    return 1 if t.errors else 0


sys.exit(asyncio.run(main()))
