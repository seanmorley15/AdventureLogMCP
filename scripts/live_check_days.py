"""A plan by day numbers only (no dates), a category reused, then dates added later."""

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _live import live  # noqa: E402


async def main() -> int:
    async with live() as t:
        col = await t.call("create_collection", name="MCP days-only check", type="plan", day_count=3, show=300)
        t.cleanup.append(f"/api/collections/{col['id']}/")
        loc = await t.call(
            "create_location", name="Day spot", latitude=64.1, longitude=-21.9, category="Waterfalls",
            collection_id=col["id"], show=0,
        )  # fmt: skip
        t.cleanup.append(f"/api/locations/{loc['id']}/")
        again = await t.call(
            "create_location", name="Day spot 2", latitude=64.2, longitude=-21.8, category="waterfall", show=0
        )
        t.cleanup.append(f"/api/locations/{again['id']}/")
        t.check("same category reused for waterfall/Waterfalls", again.get("category") == loc.get("category"))
        await t.call("schedule_item", collection_id=col["id"], kind="location", object_id=loc["id"], day=2, show=0)
        plan = await t.call("get_day_plan", collection_id=col["id"], show=600)
        t.check("3 numbered days, no dates", len(plan["days"]) == 3 and not any(d.get("date") for d in plan["days"]))
        t.check("item on day 2", any(i for d in plan["days"] if d["day"] == 2 for i in d["items"]))
        await t.call("set_plan_length", collection_id=col["id"], day_count=3, start_date="2027-07-01", show=300)
        plan = await t.call("get_day_plan", collection_id=col["id"], show=0)
        t.check("dates can be added later", plan["days"][0].get("date") == "2027-07-01")
    return 1 if t.errors else 0


sys.exit(asyncio.run(main()))
