"""Collections: a folder of locations, or a dated plan. Also holds lodgings, transportations, notes, checklists."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import shaping
from ..auth import api
from ._common import CREATE, PAGE_SIZE, READ_ONLY

IDEMPOTENT_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# Removing a link deletes the location's placement in the collection (not the location itself).
UNLINK = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_collections(
        ctx: Context,
        type: Annotated[Literal["folder", "plan"] | None, Field(description="'plan' = dated collection")] = None,
        status: Annotated[
            Literal["upcoming", "in_progress", "completed"] | None, Field(description="Plans only, by date")
        ] = None,
        membership: Annotated[
            Literal["owned", "shared"] | None, Field(description="Owned by the user, or shared with them")
        ] = None,
        archived: bool | None = None,
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=100)] = PAGE_SIZE,
    ) -> dict:
        """List the user's collections (folders and dated plans), one short entry each. Use get_collection
        for what is inside one."""
        data = await api(ctx).get(
            "/api/collections/",
            params={
                "type": "trip" if type == "plan" else type,
                "status": status,
                "membership": membership,
                "archived": None if archived is None else str(archived).lower(),
                "page": page,
                "page_size": page_size,
            },
        )
        return shaping.page(data, shaping.collection_brief, page)

    @mcp.tool(annotations=READ_ONLY)
    async def get_collection(ctx: Context, collection_id: str) -> dict:
        """Get a collection with everything in it: its locations (short entries), lodgings, transportations,
        notes and checklists."""
        return shaping.collection_full(await api(ctx).get(f"/api/collections/{collection_id}/"))

    @mcp.tool(annotations=CREATE)
    async def create_collection(
        ctx: Context,
        name: str,
        description: str | None = None,
        type: Annotated[
            Literal["folder", "plan"],
            Field(
                description=(
                    "'folder' groups locations. 'plan' is dated and gets a day-by-day itinerary "
                    "(give start_date and end_date)"
                )
            ),
        ] = "folder",
        start_date: Annotated[str | None, Field(description="YYYY-MM-DD, for plans")] = None,
        end_date: Annotated[str | None, Field(description="YYYY-MM-DD, for plans")] = None,
        timezone: Annotated[str | None, Field(description="IANA name, e.g. Europe/Lisbon")] = None,
        link: str | None = None,
    ) -> dict:
        """Create a collection. Check list_collections or search first so you do not make a duplicate.
        Safe to repeat: the identical call returns the existing collection."""
        a = api(ctx)
        body = a.create_body(
            "collection",
            name=name,
            description=description,
            type="trip" if type == "plan" else "folder",
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
            link=link,
        )
        return shaping.collection_brief(await a.post("/api/collections/", json=body))

    @mcp.tool(annotations=IDEMPOTENT_WRITE)
    async def add_location_to_collection(ctx: Context, location_id: str, collection_id: str) -> dict:
        """Put an existing location into a collection. A location can be in several collections."""
        data = await api(ctx).post(f"/api/locations/{location_id}/collections/{collection_id}/")
        return {"linked": data.get("linked", True)}

    @mcp.tool(annotations=UNLINK)
    async def remove_location_from_collection(ctx: Context, location_id: str, collection_id: str) -> dict:
        """Take a location out of a collection (including any day-plan entries for it there). The location
        itself is kept."""
        data = await api(ctx).delete(f"/api/locations/{location_id}/collections/{collection_id}/")
        return shaping.compact(
            {"linked": data.get("linked", False), "removed_day_plan_entries": data.get("removed_placements")}
        )
