"""Stage 3 against a real AdventureLog (.env): edits, version conflicts, unscheduling, deletes, prompts.

    uv run python scripts/live_smoke_stage3.py

Turns MCP_ALLOW_DESTRUCTIVE on for this run only. Cleans up after itself.
"""

import asyncio
import json
import logging
import os
import sys

os.environ["MCP_ALLOW_DESTRUCTIVE"] = "true"

import httpx  # noqa: E402

from adventurelog_mcp.client import AdventureLogClient, AdventureLogError  # noqa: E402
from adventurelog_mcp.config import get_settings  # noqa: E402
from adventurelog_mcp.server import build_http_app  # noqa: E402

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def main() -> int:
    logging.disable(logging.INFO)
    s = get_settings()
    app = build_http_app()
    failures = 0
    cleanup: list[str] = []
    checks: list[tuple[str, bool]] = []

    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mcp") as http:
                n = 0

                async def rpc(method: str, **params):
                    nonlocal n
                    n += 1
                    body = {"jsonrpc": "2.0", "id": n, "method": method, "params": params}
                    r = await http.post("/mcp", json=body, headers={**HEADERS, "X-API-Key": s.adventurelog_api_key})
                    return json.loads(r.text)["result"]

                async def call(tool: str, /, show: int = 240, expect_error: bool = False, **args):
                    nonlocal failures
                    res = await rpc("tools/call", name=tool, arguments=args)
                    text = res["content"][0]["text"]
                    ok = not res.get("isError")
                    failures += (ok == expect_error) if expect_error else (not ok)
                    arg_text = ", ".join(f"{k}={v!r}"[:30] for k, v in args.items())
                    print(f"\n{'OK ' if ok else ('ERR (expected)' if expect_error else 'ERR')} {tool}({arg_text})")
                    print("   " + " ".join(text.split())[:show])
                    return json.loads(text) if ok else text

                def check(label: str, cond: bool):
                    checks.append((label, cond))
                    print(f"   CHECK {'pass' if cond else 'FAIL'}: {label}")

                col = await call(
                    "create_collection", name="MCP smoke 3", type="plan", start_date="2027-06-03", end_date="2027-06-05"
                )
                cid = col["id"]
                cleanup.append(f"/api/collections/{cid}/")
                check("create_collection returns a version", bool(col.get("version")))
                loc = await call(
                    "create_location", name="Edit me", latitude=38.7, longitude=-9.1, collection_id=cid, tags=["a"]
                )
                cleanup.append(f"/api/locations/{loc['id']}/")
                lod = await call(
                    "create_lodging",
                    name="Hotel",
                    collection_id=cid,
                    check_in="2027-06-03T15:00",
                    check_out="2027-06-04T11:00",
                )
                tr = await call("create_transportation", name="Drive", type="car", collection_id=cid)
                note = await call("create_note", name="Tips", content="old", collection_id=cid)
                chk = await call(
                    "create_checklist",
                    name="Pack",
                    collection_id=cid,
                    items=[{"name": "Passport"}, {"name": "Charger"}],
                )
                vis = await call("log_visit", location_id=loc["id"], start_date="2027-06-04")

                print("\n--- edits")
                got = await call("get_location", location_id=loc["id"])
                v1 = got["version"]
                up = await call(
                    "update_location", location_id=loc["id"], name="Edited", rating=4.5, tags=["a", "b"], version=v1
                )
                check("update with the current version works", up["name"] == "Edited" and up["version"] != v1)
                stale = await call(
                    "update_location",
                    location_id=loc["id"],
                    name="Stale write",
                    version=v1,
                    expect_error=True,
                    show=420,
                )
                check(
                    "stale version is refused with the current record",
                    "precondition_failed" in stale and "Edited" in stale,
                )
                check(
                    "refused edit saved nothing",
                    (await call("get_location", location_id=loc["id"], show=40))["name"] == "Edited",
                )
                await call("update_location", location_id=loc["id"], description="No version given", show=100)
                await call("update_location", location_id=loc["id"], expect_error=True, show=160)  # nothing to change
                await call("update_collection", collection_id=cid, name="MCP smoke 3 (renamed)", description="hello")
                moved = await call("update_collection", collection_id=cid, start_date="2027-07-01")
                check(
                    "start date moved, length kept",
                    moved["start_date"] == "2027-07-01" and moved["end_date"] == "2027-07-03",
                )
                await call(
                    "update_lodging", lodging_id=lod["id"], check_out="2027-07-02T11:00", reservation_number="ABC123"
                )
                await call("update_transportation", transportation_id=tr["id"], from_place="A", to_place="B")
                await call("update_note", note_id=note["id"], content="new text")
                ticked = await call(
                    "update_checklist",
                    checklist_id=chk["id"],
                    items=[{"name": "Passport", "is_checked": True}, {"name": "Charger"}],
                )
                check("checklist item ticked", ticked["items"][0]["is_checked"] is True)
                await call("update_visit", visit_id=vis["id"], notes="Sunset")

                print("\n--- unscheduling")
                await call("schedule_item", collection_id=cid, kind="location", object_id=loc["id"], day=1, show=60)
                plan = await call("get_day_plan", collection_id=cid, show=60)
                item_id = plan["days"][0]["items"][0]["item_id"]
                after = await call("remove_plan_item", collection_id=cid, item_id=item_id, show=60)
                check(
                    "record stays in the collection, now unscheduled",
                    any(r["id"] == loc["id"] for r in after["not_scheduled_yet"]["location"]),
                )

                print("\n--- deletes (MCP_ALLOW_DESTRUCTIVE=true)")
                await call("delete_visit", visit_id=vis["id"])
                await call("delete_note", note_id=note["id"])
                await call("delete_checklist", checklist_id=chk["id"])
                await call("delete_transportation", transportation_id=tr["id"])
                await call("delete_lodging", lodging_id=lod["id"])
                await call("delete_collection", collection_id=cid)
                check(
                    "deleting the collection kept its location",
                    "name" in await call("get_location", location_id=loc["id"], show=40),
                )
                await call("delete_location", location_id=loc["id"])
                await call("delete_location", location_id=loc["id"], expect_error=True, show=120)  # already gone

                print("\n--- prompts")
                listed = await rpc("prompts/list")
                print("   prompts:", [p["name"] for p in listed["prompts"]])
                got = await rpc(
                    "prompts/get", name="plan_collection", arguments={"destination": "Lisbon", "dates": "June 3-6 2027"}
                )
                check("plan_collection prompt renders", "Lisbon" in got["messages"][0]["content"]["text"])
    finally:
        client = AdventureLogClient()
        key = s.adventurelog_api_key
        for path in reversed(cleanup):
            try:
                await client.delete(path, api_key=key)
            except AdventureLogError:
                pass  # already deleted by the test itself
        left = [(await client.get(p, api_key=key))["count"] for p in ("/api/collections/", "/api/locations/")]
        await client.aclose()
        print(f"\nleft behind: {left[0]} collections, {left[1]} locations")
    bad = [label for label, ok in checks if not ok]
    print(f"{len(checks) - len(bad)}/{len(checks)} checks passed; {failures} unexpected tool errors")
    return 1 if bad or failures else 0


sys.exit(asyncio.run(main()))
