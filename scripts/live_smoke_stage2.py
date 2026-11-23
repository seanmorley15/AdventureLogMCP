"""Stage 2 against a real AdventureLog (.env): day plan + world travel. Cleans up after itself.

uv run python scripts/live_smoke_stage2.py
"""

import asyncio
import json
import logging
import sys

import httpx

from adventurelog_mcp.client import AdventureLogClient, AdventureLogError
from adventurelog_mcp.config import get_settings
from adventurelog_mcp.server import build_http_app

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def main() -> int:
    logging.disable(logging.INFO)
    s = get_settings()
    app = build_http_app()
    failures = 0
    cleanup: list[str] = []

    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as http:
                n = 0

                async def call(tool: str, /, show: int = 260, **args):
                    nonlocal n, failures
                    n += 1
                    body = {
                        "jsonrpc": "2.0",
                        "id": n,
                        "method": "tools/call",
                        "params": {"name": tool, "arguments": args},
                    }
                    r = await http.post("/mcp", json=body, headers={**HEADERS, "X-API-Key": s.adventurelog_api_key})
                    res = json.loads(r.text)["result"]
                    text = res["content"][0]["text"]
                    ok = not res.get("isError")
                    failures += not ok
                    arg_text = ", ".join(f"{k}={v!r}"[:34] for k, v in args.items())
                    print(f"\n{'OK ' if ok else 'ERR'} {tool}({arg_text})")
                    print("   " + " ".join(text.split())[:show])
                    return json.loads(text) if ok else None

                col = await call("create_collection", name="MCP smoke 2: Lisbon", type="plan",
                                 start_date="2027-06-03", end_date="2027-06-05")  # fmt: skip
                cid = col["id"]
                cleanup.append(f"/api/collections/{cid}/")
                a = await call("create_location", name="Castelo de S. Jorge", latitude=38.7139, longitude=-9.1334,
                               collection_id=cid)  # fmt: skip
                b = await call(
                    "create_location", name="Time Out Market", latitude=38.707, longitude=-9.1456, collection_id=cid
                )
                c = await call(
                    "create_location", name="Belem Tower", latitude=38.6916, longitude=-9.216, collection_id=cid
                )
                cleanup += [f"/api/locations/{x['id']}/" for x in (a, b, c)]
                hotel = await call("create_lodging", name="Hotel Avenida Palace", collection_id=cid, type="hotel",
                                   check_in="2027-06-03T15:00", check_out="2027-06-05T11:00")  # fmt: skip
                note = await call("create_note", name="Tips", content="Tram 28 early", collection_id=cid)
                await call("get_day_plan", collection_id=cid, show=700)

                await call(
                    "schedule_item",
                    collection_id=cid,
                    kind="location",
                    object_id=a["id"],
                    day=1,
                    start_time="10:00",
                    show=500,
                )
                await call(
                    "schedule_item",
                    collection_id=cid,
                    kind="location",
                    object_id=b["id"],
                    day=1,
                    start_time="13:00",
                    show=100,
                )
                await call(
                    "schedule_item",
                    collection_id=cid,
                    kind="lodging",
                    object_id=hotel["id"],
                    day=1,
                    through_day=3,
                    show=100,
                )
                await call(
                    "schedule_item", collection_id=cid, kind="note", object_id=note["id"], trip_wide=True, show=100
                )
                await call("schedule_item", collection_id=cid, kind="location", object_id=c["id"], show=100)  # Ideas
                await call("schedule_item", collection_id=cid, kind="location", object_id=c["id"], show=120)  # repeat
                await call(
                    "schedule_item", collection_id=cid, kind="location", object_id=c["id"], day=2, show=120
                )  # Ideas -> day
                await call(
                    "schedule_item", collection_id=cid, kind="location", object_id=c["id"], day=2, show=120
                )  # repeat
                await call("move_plan_item", collection_id=cid, item_id="x", show=200)  # bad id -> clean error
                plan = await call("get_day_plan", collection_id=cid, show=1500)
                day1 = plan["days"][0]["items"]
                await call("order_day_items", collection_id=cid, day=1, item_ids=[day1[-1]["item_id"]], show=100)
                after = await call("get_day_plan", collection_id=cid, show=100)
                print("   day 1 order now:", [i["name"] for i in after["days"][0]["items"]])
                await call("order_day_items", collection_id=cid, day=1, item_ids=["nope"], show=200)
                belem = plan["days"][1]["items"][0]["item_id"]
                await call("move_plan_item", collection_id=cid, item_id=belem, to_ideas=True, show=100)
                await call("order_day_items", collection_id=cid, day=3, item_ids=[belem], show=100)  # Ideas -> day 3
                await call("move_plan_item", collection_id=cid, item_id=belem, day=2, start_time="09:00", show=100)
                await call("set_day_details", collection_id=cid, day=2, name="Belem", description="Monuments", show=100)
                await call("set_day_details", collection_id=cid, day=9, name="Nope", show=200)
                await call("set_plan_length", collection_id=cid, day_count=4, show=100)
                await call("set_plan_length", collection_id=cid, day_count=1, show=300)  # items on removed days
                await call("set_plan_length", collection_id=cid, day_count=2, removed_items_go_to="ideas", show=100)
                await call("shift_plan_dates", collection_id=cid, days=7, show=1400)
                await call("recommend_nearby", near="Alfama, Lisbon", category="food", limit=2, show=500)

                print("\n--- world travel")
                await call("list_countries", query="portug")
                await call("get_country", country_code="pt")
                regs = await call("list_regions", country_code="PT", query="lisb", show=300)
                rid = regs["regions"][0]["id"]
                await call("list_cities", region_id=rid, query="lisbon", limit=3, show=300)
                cleanup.append(f"visited-region:{rid}")
                await call("mark_region_visited", region_id=rid)
                await call("list_regions", country_code="PT", visited=True)
                await call("list_countries", visited_only=True)
                cities = await call("list_cities", region_id=rid, limit=1, show=200)
                cid2 = cities["cities"][0]["id"]
                cleanup.append(f"visited-city:{cid2}")
                await call("mark_city_visited", city_id=cid2)
                await call("list_cities", region_id=rid, visited=True, show=300)
                await call("get_travel_stats", show=500)
                await call("unmark_city_visited", city_id=cid2)
                await call("unmark_region_visited", region_id=rid)
                await call("list_regions", country_code="PT", visited=True, show=100)
                await call("sync_visited_regions")
    finally:
        client = AdventureLogClient()
        key = s.adventurelog_api_key
        for path in reversed(cleanup):
            try:
                if path.startswith("visited-city:"):
                    await client.delete(f"/api/visited-cities/{path.split(':', 1)[1]}/", api_key=key)
                elif path.startswith("visited-region:"):
                    await client.delete(f"/api/visited-regions/{path.split(':', 1)[1]}/", api_key=key)
                else:
                    await client.delete(path, api_key=key)
            except AdventureLogError:
                pass  # already gone (or never marked)
        left = [
            (await client.get("/api/collections/", api_key=key))["count"],
            (await client.get("/api/locations/", api_key=key))["count"],
            len(await client.get("/api/visited-regions/", api_key=key)),
        ]
        await client.aclose()
        print(f"\nleft behind: {left[0]} collections, {left[1]} locations, {left[2]} visited regions")
    print(f"{failures} tool errors (expected: bad item id x2, day 9, shrinking without a destination)")
    return 0


sys.exit(asyncio.run(main()))
