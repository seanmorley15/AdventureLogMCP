"""Walk the Stage 1 flow against a real AdventureLog (uses .env: ADVENTURELOG_URL + ADVENTURELOG_API_KEY).

    uv run python scripts/live_smoke.py

Creates a throwaway collection and everything in it, prints what the model would see, then deletes it.
"""

import asyncio
import json
import logging
import sys

import httpx

from adventurelog_mcp.client import AdventureLogClient
from adventurelog_mcp.config import get_settings
from adventurelog_mcp.server import build_http_app

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def main() -> int:
    logging.disable(logging.INFO)
    s = get_settings()
    app = build_http_app()
    failures = 0
    created: list[tuple[str, str]] = []  # (path, id) to clean up

    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as http:
                n = 0

                async def call(tool: str, /, **args):
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
                    print(f"\n{'OK ' if ok else 'ERR'} {tool}({', '.join(f'{k}={v!r}'[:40] for k, v in args.items())})")
                    print("   " + text.replace("\n", " ")[:400])
                    return json.loads(text) if ok else None

                await call("whoami")
                col = await call(
                    "create_collection",
                    name="MCP smoke: Lisbon",
                    type="plan",
                    start_date="2027-06-03",
                    end_date="2027-06-06",
                    timezone="Europe/Lisbon",
                    description="Created by the MCP live smoke test",
                )
                again = await call(
                    "create_collection",
                    name="MCP smoke: Lisbon",
                    type="plan",
                    start_date="2027-06-03",
                    end_date="2027-06-06",
                    timezone="Europe/Lisbon",
                    description="Created by the MCP live smoke test",
                )
                cid = col["id"]
                created.append(("/api/collections/", cid))

                places = await call("search_places", query="Time Out Market Lisbon", limit=2)
                p = (places or {}).get("results", [{}])[0]
                if p:
                    await call(
                        "check_duplicate_locations", name=p["name"], latitude=p["latitude"], longitude=p["longitude"]
                    )
                loc = await call(
                    "create_location",
                    name="Miradouro da Senhora do Monte",
                    latitude=38.7194,
                    longitude=-9.1327,
                    address="Lisbon, Portugal",
                    category="general",
                    tags=["viewpoint"],
                    rating=4.5,
                    collection_id=cid,
                    visits=[{"start_date": "2027-06-04", "end_date": "2027-06-04", "notes": "Sunset"}],
                )
                if loc:
                    created.append(("/api/locations/", loc["id"]))
                loc2 = await call("create_location", name="Castelo de S. Jorge", latitude=38.7139, longitude=-9.1334)
                if loc2:
                    created.append(("/api/locations/", loc2["id"]))
                    await call("add_location_to_collection", location_id=loc2["id"], collection_id=cid)
                await call(
                    "create_lodging",
                    name="Hotel Avenida Palace",
                    collection_id=cid,
                    type="hotel",
                    check_in="2027-06-03T15:00",
                    check_out="2027-06-06T11:00",
                    address="Lisbon",
                    latitude=38.7147,
                    longitude=-9.1403,
                )
                await call(
                    "create_transportation",
                    name="TAP TP204 JFK to LIS",
                    type="plane",
                    collection_id=cid,
                    start="2027-06-02T21:30",
                    end="2027-06-03T09:15",
                    from_place="New York JFK",
                    to_place="Lisbon LIS",
                    flight_number="TP204",
                    start_code="JFK",
                    end_code="LIS",
                    start_timezone="America/New_York",
                    end_timezone="Europe/Lisbon",
                )
                await call("create_note", name="Tips", content="Book the tram 28 early.", collection_id=cid)
                await call(
                    "create_checklist",
                    name="Packing",
                    collection_id=cid,
                    items=[{"name": "Passport"}, {"name": "Adapter"}],
                )
                await call("log_visit", location_id=loc2["id"], start_date="2027-06-05") if loc2 else None
                await call("get_collection", collection_id=cid)
                await call("get_location", location_id=loc["id"]) if loc else None
                await call("list_collections", type="plan")
                await call("list_locations", is_visited=True, page_size=3)
                await call("search", query="Lisbon")
                await call("list_categories")
                await call("list_tags")
                await call(
                    "remove_location_from_collection", location_id=loc2["id"], collection_id=cid
                ) if loc2 else None
                print("\nretry returned the same collection:", bool(again) and again["id"] == cid)
    finally:
        client = AdventureLogClient()
        for path, rid in reversed(created):
            await client.delete(f"{path}{rid}/", api_key=s.adventurelog_api_key)
        await client.aclose()
    print(f"\ncleaned up {len(created)} records; {failures} tool errors")
    return 1 if failures else 0


sys.exit(asyncio.run(main()))
