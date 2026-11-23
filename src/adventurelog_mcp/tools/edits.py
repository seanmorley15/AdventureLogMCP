"""Change existing records. Only the fields you pass are changed; pass an empty string to clear a text field."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import shaping
from ..auth import api
from ._common import DESCRIBE, category_fields
from .collection_items import ChecklistItemInput

EDIT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

VERSION = Field(
    description="`version` from get_location/get_collection. If the record changed since, nothing is saved and "
    "you get its current state instead."
)


def _changes(**fields) -> dict:
    body = {k: v for k, v in fields.items() if v is not None}
    if not body:
        raise ToolError("Nothing to change: pass at least one field to update.")
    return body


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=EDIT)
    async def update_location(
        ctx: Context,
        location_id: str,
        name: str | None = None,
        description: Annotated[str | None, Field(description=DESCRIBE)] = None,
        address: str | None = None,
        latitude: Annotated[float | None, Field(ge=-90, le=90)] = None,
        longitude: Annotated[float | None, Field(ge=-180, le=180)] = None,
        category: Annotated[str | None, Field(description="Category name; see list_categories")] = None,
        tags: Annotated[list[str] | None, Field(description="The full new list of tags (replaces the old one)")] = None,
        rating: Annotated[float | None, Field(ge=0, le=5)] = None,
        link: str | None = None,
        price: str | None = None,
        is_public: bool | None = None,
        version: Annotated[str | None, VERSION] = None,
    ) -> dict:
        """Change a saved location. Visits are changed with update_visit / log_visit."""
        body = _changes(
            name=name,
            description=description,
            location=address,
            latitude=latitude,
            longitude=longitude,
            category=category_fields(category) if category else None,
            tags=tags,
            rating=rating,
            link=link,
            price=price,
            is_public=is_public,
        )
        data, etag = await api(ctx).patch(
            f"/api/locations/{location_id}/",
            json=body,
            version=version,
            shape_current=shaping.location_full,
            with_etag=True,
        )
        return shaping.versioned(shaping.location_full(data), etag)

    @mcp.tool(annotations=EDIT)
    async def update_collection(
        ctx: Context,
        collection_id: str,
        name: str | None = None,
        description: str | None = None,
        type: Annotated[
            Literal["folder", "plan"] | None, Field(description="Turn a folder into a dated plan, or back")
        ] = None,
        start_date: Annotated[str | None, Field(description="YYYY-MM-DD: the new first day of a plan")] = None,
        link: str | None = None,
        archived: bool | None = None,
        version: Annotated[str | None, VERSION] = None,
    ) -> dict:
        """Change a collection's name, description, start date or type. A plan's end date follows from its start
        date and number of days: to make it longer or shorter use set_plan_length, to move it by some days use
        shift_plan_dates."""
        body = _changes(
            name=name,
            description=description,
            type=None if type is None else ("trip" if type == "plan" else "folder"),
            start_date=start_date,
            link=link,
            is_archived=archived,
        )
        data, etag = await api(ctx).patch(
            f"/api/collections/{collection_id}/",
            json=body,
            version=version,
            shape_current=shaping.collection_brief,
            with_etag=True,
        )
        return shaping.versioned(shaping.collection_brief(data), etag)

    @mcp.tool(annotations=EDIT)
    async def update_lodging(
        ctx: Context,
        lodging_id: str,
        name: str | None = None,
        type: Literal[
            "hotel", "hostel", "resort", "bnb", "campground", "cabin", "apartment", "house", "villa", "motel", "other"
        ]
        | None = None,
        check_in: Annotated[str | None, Field(description="ISO datetime")] = None,
        check_out: Annotated[str | None, Field(description="ISO datetime")] = None,
        address: str | None = None,
        latitude: Annotated[float | None, Field(ge=-90, le=90)] = None,
        longitude: Annotated[float | None, Field(ge=-180, le=180)] = None,
        reservation_number: str | None = None,
        price: str | None = None,
        link: str | None = None,
        description: str | None = None,
        timezone: str | None = None,
    ) -> dict:
        """Change a lodging in a collection (find its id with get_collection)."""
        body = _changes(
            name=name, type=type, check_in=check_in, check_out=check_out, location=address, latitude=latitude,
            longitude=longitude, reservation_number=reservation_number, price=price, link=link,
            description=description, timezone=timezone,
        )  # fmt: skip
        return shaping.lodging(await api(ctx).patch(f"/api/lodgings/{lodging_id}/", json=body))

    @mcp.tool(annotations=EDIT)
    async def update_transportation(
        ctx: Context,
        transportation_id: str,
        name: str | None = None,
        type: Literal["car", "motorcycle", "plane", "train", "bus", "boat", "bike", "walking", "other"] | None = None,
        start: Annotated[str | None, Field(description="Departure, ISO datetime")] = None,
        end: Annotated[str | None, Field(description="Arrival, ISO datetime")] = None,
        from_place: str | None = None,
        to_place: str | None = None,
        flight_number: str | None = None,
        start_code: str | None = None,
        end_code: str | None = None,
        start_timezone: str | None = None,
        end_timezone: str | None = None,
        price: str | None = None,
        link: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Change a flight, train or other transportation in a collection (find its id with get_collection)."""
        body = _changes(
            name=name, type=type, date=start, end_date=end, from_location=from_place, to_location=to_place,
            flight_number=flight_number, start_code=start_code, end_code=end_code, start_timezone=start_timezone,
            end_timezone=end_timezone, price=price, link=link, description=description,
        )  # fmt: skip
        return shaping.transportation(await api(ctx).patch(f"/api/transportations/{transportation_id}/", json=body))

    @mcp.tool(annotations=EDIT)
    async def update_note(
        ctx: Context,
        note_id: str,
        name: str | None = None,
        content: Annotated[str | None, Field(description="The new full text (replaces the old)")] = None,
        date: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
        links: Annotated[list[str] | None, Field(description="The full new list of links")] = None,
    ) -> dict:
        """Change a note (find its id with get_collection)."""
        body = _changes(name=name, content=content, date=date, links=links)
        return shaping.note(await api(ctx).patch(f"/api/notes/{note_id}/", json=body))

    @mcp.tool(annotations=EDIT)
    async def update_checklist(
        ctx: Context,
        checklist_id: str,
        name: str | None = None,
        items: Annotated[
            list[ChecklistItemInput] | None,
            Field(description="The FULL new list of items with their checked state (replaces the old list)"),
        ] = None,
        date: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    ) -> dict:
        """Change a checklist: rename it, or replace its items (to tick one off, send every item, with that one
        `is_checked: true`). Find the current items with get_collection."""
        body = _changes(name=name, date=date, items=[i.model_dump() for i in items] if items is not None else None)
        return shaping.checklist(await api(ctx).patch(f"/api/checklists/{checklist_id}/", json=body))

    @mcp.tool(annotations=EDIT)
    async def update_visit(
        ctx: Context,
        visit_id: Annotated[str, Field(description="Visit id from get_location")],
        start_date: Annotated[str | None, Field(description="ISO date/datetime")] = None,
        end_date: str | None = None,
        notes: str | None = None,
    ) -> dict:
        """Change a visit's dates or notes."""
        body = _changes(start_date=start_date, end_date=end_date, notes=notes)
        return shaping.visit(await api(ctx).patch(f"/api/visits/{visit_id}/", json=body))
