"""What lives inside a collection: lodgings, transportations, notes and checklists."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from pydantic import BaseModel, Field

from .. import shaping
from ..auth import api
from ..client import new_id
from ._common import CREATE

COLLECTION = Field(description="Collection to put it in (from create_collection / list_collections)")


class ChecklistItemInput(BaseModel):
    name: str
    is_checked: bool = False


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=CREATE)
    async def create_lodging(
        ctx: Context,
        name: str,
        collection_id: Annotated[str | None, COLLECTION] = None,
        type: Literal[
            "hotel", "hostel", "resort", "bnb", "campground", "cabin", "apartment", "house", "villa", "motel", "other"
        ] = "hotel",
        check_in: Annotated[str | None, Field(description="ISO datetime, e.g. 2026-06-03T15:00")] = None,
        check_out: Annotated[str | None, Field(description="ISO datetime")] = None,
        address: str | None = None,
        latitude: Annotated[float | None, Field(ge=-90, le=90)] = None,
        longitude: Annotated[float | None, Field(ge=-180, le=180)] = None,
        reservation_number: str | None = None,
        price: str | None = None,
        link: str | None = None,
        description: str | None = None,
        timezone: Annotated[str | None, Field(description="IANA name for check_in/check_out")] = None,
    ) -> dict:
        """Add a place to stay (hotel, rental, campsite...) to a collection.

        Safe to repeat: the identical call returns the existing record."""
        a = api(ctx)
        body = a.create_body(
            "lodging",
            name=name, collection=collection_id, type=type, check_in=check_in, check_out=check_out, location=address,
            latitude=latitude, longitude=longitude, reservation_number=reservation_number, price=price, link=link,
            description=description, timezone=timezone,
        )  # fmt: skip
        return shaping.lodging(await a.post("/api/lodgings/", json=body))

    @mcp.tool(annotations=CREATE)
    async def create_transportation(
        ctx: Context,
        name: Annotated[str, Field(description="e.g. 'TAP TP1234 JFK to LIS'")],
        type: Literal["car", "motorcycle", "plane", "train", "bus", "boat", "bike", "walking", "other"],
        collection_id: Annotated[str | None, COLLECTION] = None,
        start: Annotated[str | None, Field(description="Departure, ISO datetime")] = None,
        end: Annotated[str | None, Field(description="Arrival, ISO datetime")] = None,
        from_place: Annotated[str | None, Field(description="Origin name or address")] = None,
        to_place: Annotated[str | None, Field(description="Destination name or address")] = None,
        flight_number: str | None = None,
        start_code: Annotated[str | None, Field(description="Origin code, e.g. airport IATA 'JFK'")] = None,
        end_code: Annotated[str | None, Field(description="Destination code, e.g. 'LIS'")] = None,
        origin_latitude: float | None = None,
        origin_longitude: float | None = None,
        destination_latitude: float | None = None,
        destination_longitude: float | None = None,
        start_timezone: Annotated[str | None, Field(description="IANA name for the departure time")] = None,
        end_timezone: Annotated[str | None, Field(description="IANA name for the arrival time")] = None,
        price: str | None = None,
        link: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Add a flight, train, drive or other way of getting around to a collection.

        Safe to repeat: the identical call returns the existing record."""
        a = api(ctx)
        body = a.create_body(
            "transportation",
            name=name, type=type, collection=collection_id, date=start, end_date=end, from_location=from_place,
            to_location=to_place, flight_number=flight_number, start_code=start_code, end_code=end_code,
            origin_latitude=origin_latitude, origin_longitude=origin_longitude,
            destination_latitude=destination_latitude, destination_longitude=destination_longitude,
            start_timezone=start_timezone, end_timezone=end_timezone, price=price, link=link, description=description,
        )  # fmt: skip
        return shaping.transportation(await a.post("/api/transportations/", json=body))

    @mcp.tool(annotations=CREATE)
    async def create_note(
        ctx: Context,
        name: str,
        content: Annotated[str | None, Field(description="The note text (Markdown is fine)")] = None,
        collection_id: Annotated[str | None, COLLECTION] = None,
        date: Annotated[str | None, Field(description="YYYY-MM-DD the note belongs to")] = None,
        links: list[str] | None = None,
    ) -> dict:
        """Add a note to a collection: tips, reservations, ideas, anything free-form.

        Safe to repeat: the identical call returns the existing record."""
        a = api(ctx)
        body = a.create_body("note", name=name, content=content, collection=collection_id, date=date, links=links)
        return shaping.note(await a.post("/api/notes/", json=body))

    @mcp.tool(annotations=CREATE)
    async def create_checklist(
        ctx: Context,
        name: Annotated[str, Field(description="e.g. 'Packing list'")],
        items: Annotated[list[ChecklistItemInput], Field(description="Checklist entries, in order")],
        collection_id: Annotated[str | None, COLLECTION] = None,
        date: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    ) -> dict:
        """Add a checklist (packing list, to-dos) with its items to a collection.

        Safe to repeat: the identical call returns the existing record."""
        a = api(ctx)
        body = a.create_body(
            "checklist",
            name=name, collection=collection_id, date=date,
            items=[{"id": new_id(), **i.model_dump()} for i in items],
        )  # fmt: skip
        return shaping.checklist(await a.post("/api/checklists/", json=body))
