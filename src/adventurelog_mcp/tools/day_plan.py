"""The day-by-day plan of a dated collection (a 'plan'): which locations, stays, journeys and notes go on which day."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import shaping
from ..auth import api
from ._common import EXTERNAL, READ_ONLY

Kind = Literal["location", "lodging", "transportation", "note", "checklist"]
# Plan edits change the plan, never delete a record.
EDIT_SAME = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

DAY = Field(ge=1, description="Day number, 1 = the first day of the plan")
TIME = Field(description="Clock time HH:MM (24h), e.g. 09:30")


def _bucket(item: dict):
    """Where a plan item sits: 'trip_wide', 'ideas', or its day number."""
    if item.get("is_global"):
        return "trip_wide"
    return item.get("day_index") or "ideas"


async def _plan(a, collection_id: str) -> dict:
    plan = await a.get(f"/api/collections/{collection_id}/itinerary/")
    collection = await a.get(f"/api/collections/{collection_id}/")
    return shaping.day_plan(plan, collection)


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def get_day_plan(ctx: Context, collection_id: str) -> dict:
        """Get the day-by-day plan of a dated collection: each day with its date and ordered, named items
        (times, optional, multi-day stays), then Ideas (in the collection, no day yet), trip-wide items, and
        `not_scheduled_yet` (everything in the collection that is not on the plan). Items are the records
        created with create_location, create_lodging and so on, so use their object_id to schedule more."""
        return await _plan(api(ctx), collection_id)

    @mcp.tool(annotations=EDIT_SAME)
    async def schedule_item(
        ctx: Context,
        collection_id: str,
        kind: Annotated[Kind, Field(description="What is being placed")],
        object_id: Annotated[str, Field(description="Id of the location/lodging/transportation/note/checklist")],
        day: Annotated[int | None, DAY] = None,
        date: Annotated[str | None, Field(description="YYYY-MM-DD, instead of `day`")] = None,
        trip_wide: Annotated[bool, Field(description="Not tied to one day (notes and checklists)")] = False,
        start_time: Annotated[str | None, TIME] = None,
        end_time: Annotated[str | None, TIME] = None,
        timezone: Annotated[str | None, Field(description="IANA name for the times")] = None,
        order: Annotated[int | None, Field(ge=0, description="Position on the day; default: last")] = None,
        through_day: Annotated[
            int | None, Field(ge=1, description="Stays and journeys: the last day they cover")
        ] = None,
        optional: bool = False,
    ) -> dict:
        """Put a record that is already in the collection onto the plan. Give `day` (or `date`) for a day,
        `trip_wide` for the whole plan, or neither to park it in Ideas. Placing a lodging or transportation
        sets its dates from the day. It does not log a visit.

        Repeating the call changes nothing, and a record parked in Ideas is moved to the day instead of
        being added twice. To put the same location on a second day, call it again with that day."""
        a = api(ctx)
        plan = await a.get(f"/api/collections/{collection_id}/itinerary/")
        if date and day is None:
            match = next((d for d in plan.get("itinerary_days", []) if d.get("date") == date), None)
            if not match:
                raise ToolError(f"{date} is not a day of this plan; use set_plan_length or shift_plan_dates first.")
            day = match["index"]
        target = "trip_wide" if trip_wide else (day or "ideas")
        existing = [
            i for i in plan.get("itinerary", []) if i.get("content_type") == kind and i.get("object_id") == object_id
        ]
        fields = {
            "start_time": start_time,
            "end_time": end_time,
            "timezone": timezone,
            "order": order,
            "span_end_index": through_day,
            "is_optional": optional or None,
        }
        fields = {k: v for k, v in fields.items() if v is not None}

        note = None
        if any(_bucket(i) == target for i in existing):
            note = "Already scheduled there; nothing changed."
        elif target != "ideas" and (parked := next((i for i in existing if _bucket(i) == "ideas"), None)):
            move = {**fields, "is_global": True} if trip_wide else {**fields, "day_index": day, "is_global": False}
            await a.patch(f"/api/collections/{collection_id}/itinerary-items/{parked['id']}/", json=move)
            note = "Moved from Ideas."
        else:
            body = {"content_type": kind, "object_id": object_id, **fields}
            if trip_wide:
                body["is_global"] = True
            elif day is not None:
                body["day_index"] = day
            await a.post(f"/api/collections/{collection_id}/itinerary-items/", json=body)
        result = await _plan(a, collection_id)
        return {"note": note, **result} if note else result

    @mcp.tool(annotations=EDIT_SAME)
    async def move_plan_item(
        ctx: Context,
        collection_id: str,
        item_id: Annotated[str, Field(description="item_id from get_day_plan")],
        day: Annotated[int | None, DAY] = None,
        trip_wide: bool = False,
        to_ideas: Annotated[bool, Field(description="Take it off its day and park it in Ideas")] = False,
        order: Annotated[int | None, Field(ge=0, description="Position on the day")] = None,
        start_time: Annotated[str | None, TIME] = None,
        end_time: Annotated[str | None, TIME] = None,
        timezone: str | None = None,
        through_day: Annotated[int | None, Field(ge=1)] = None,
        optional: bool | None = None,
    ) -> dict:
        """Move or change one item already on the plan: another day, another position, Ideas, or its times.
        Other items on the day close up around it. The record itself is not touched."""
        body: dict = {
            "day_index": day,
            "order": order,
            "start_time": start_time,
            "end_time": end_time,
            "timezone": timezone,
            "span_end_index": through_day,
            "is_optional": optional,
        }
        body = {k: v for k, v in body.items() if v is not None}
        if trip_wide:
            body["is_global"] = True
        elif to_ideas:
            body.update(day_index=None, is_global=False)
        elif day is not None:
            body["is_global"] = False
        a = api(ctx)
        await a.patch(f"/api/collections/{collection_id}/itinerary-items/{item_id}/", json=body)
        return await _plan(a, collection_id)

    @mcp.tool(annotations=EDIT_SAME)
    async def order_day_items(
        ctx: Context,
        collection_id: str,
        day: Annotated[int, DAY],
        item_ids: Annotated[
            list[str], Field(description="item_ids in the order they should happen on this day, earliest first")
        ],
    ) -> dict:
        """Put a day's items in a new order. List the items in the order you want; any items on the day that you
        leave out follow after them. Items listed from another day or Ideas are moved onto this day. Use
        start_time on schedule_item or move_plan_item to give items clock times."""
        a = api(ctx)
        plan = await a.get(f"/api/collections/{collection_id}/itinerary/")
        on_day = [
            i for i in sorted(plan.get("itinerary", []), key=lambda i: i.get("order") or 0) if i.get("day_index") == day
        ]
        known = {i["id"] for i in plan.get("itinerary", [])}
        unknown = [x for x in item_ids if x not in known]
        if unknown:
            raise ToolError(f"Not plan items of this collection: {', '.join(unknown)}. Use item_id from get_day_plan.")
        ordered = list(dict.fromkeys(item_ids)) + [i["id"] for i in on_day if i["id"] not in item_ids]
        entries = [{"id": iid, "order": n, "day_index": day, "is_global": False} for n, iid in enumerate(ordered)]
        await a.post(f"/api/collections/{collection_id}/itinerary/reorder/", json={"items": entries})
        return await _plan(a, collection_id)

    @mcp.tool(annotations=EDIT_SAME)
    async def set_day_details(
        ctx: Context,
        collection_id: str,
        day: Annotated[int, DAY],
        name: Annotated[str | None, Field(description="e.g. 'Sintra day trip'")] = None,
        description: str | None = None,
    ) -> dict:
        """Name a day or give it a description."""
        a = api(ctx)
        plan = await a.get(f"/api/collections/{collection_id}/itinerary/")
        match = next((d for d in plan.get("itinerary_days", []) if d.get("index") == day), None)
        if not match:
            raise ToolError(f"The plan has {len(plan.get('itinerary_days', []))} days; there is no day {day}.")
        body = {k: v for k, v in {"name": name, "description": description}.items() if v is not None}
        await a.patch(f"/api/collections/{collection_id}/days/{match['id']}/", json=body)
        return await _plan(a, collection_id)

    @mcp.tool(annotations=EDIT_SAME)
    async def set_plan_length(
        ctx: Context,
        collection_id: str,
        day_count: Annotated[int, Field(ge=1, description="How many days the plan should have")],
        start_date: Annotated[str | None, Field(description="YYYY-MM-DD: also set or move the first day")] = None,
        removed_items_go_to: Annotated[
            Literal["ideas", "day"] | None,
            Field(description="When shortening: send items from removed days to Ideas, or to `target_day`"),
        ] = None,
        target_day_id: Annotated[
            str | None, Field(description="With 'day': the id of the day (from get_day_plan)")
        ] = None,
    ) -> dict:
        """Make the plan longer or shorter. Shortening a plan that has items on the removed days needs
        `removed_items_go_to`. The end date follows."""
        body = {
            "day_count": day_count,
            "start_date": start_date,
            "destination": removed_items_go_to,
            "target_day": target_day_id,
        }
        a = api(ctx)
        await a.post(
            f"/api/collections/{collection_id}/itinerary/duration/",
            json={k: v for k, v in body.items() if v is not None},
        )
        return await _plan(a, collection_id)

    @mcp.tool(annotations=EDIT_SAME)
    async def shift_plan_dates(
        ctx: Context,
        collection_id: str,
        days: Annotated[
            int | None, Field(description="Move the whole plan this many days (negative = earlier)")
        ] = None,
        start_date: Annotated[str | None, Field(description="Or: the new first day, YYYY-MM-DD")] = None,
    ) -> dict:
        """Move a dated plan to other dates. Days, order and times stay; visits already logged do not move."""
        body = {k: v for k, v in {"days": days, "start_date": start_date}.items() if v is not None}
        a = api(ctx)
        await a.post(f"/api/collections/{collection_id}/itinerary/shift/", json=body)
        return await _plan(a, collection_id)

    @mcp.tool(annotations=EXTERNAL)
    async def recommend_nearby(
        ctx: Context,
        near: Annotated[str | None, Field(description="A place name to search around, e.g. 'Alfama, Lisbon'")] = None,
        latitude: Annotated[float | None, Field(ge=-90, le=90)] = None,
        longitude: Annotated[float | None, Field(ge=-180, le=180)] = None,
        category: Annotated[
            Literal["attractions", "culture", "nature", "food", "nightlife", "lodging", "activities"] | None,
            Field(description="What to look for"),
        ] = None,
        radius_meters: Annotated[int, Field(ge=100, le=50000)] = 5000,
        limit: Annotated[int, Field(ge=1, le=20)] = 8,
    ) -> dict:
        """Find things to see, eat or stay near a point, ranked by quality and distance. Give `near` (a name)
        or latitude and longitude, for example a collection's hotel. Results are not saved: use
        save_place_as_location to keep one."""
        data = await api(ctx).get(
            "/api/recommendations/",
            params={
                "location": near,
                "lat": latitude,
                "lon": longitude,
                "category": category,
                "radius": radius_meters,
                "limit": limit,
            },
        )
        return shaping.compact(
            {"results": [shaping.recommendation(r) for r in data.get("results", [])], "warnings": data.get("warnings")}
        )
