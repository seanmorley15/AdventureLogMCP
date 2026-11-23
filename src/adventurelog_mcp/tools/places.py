"""Place search: look up real-world places before saving them. A place is not a location until it is saved."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from .. import shaping
from ..auth import api
from ._common import EXTERNAL


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=EXTERNAL)
    async def search_places(
        ctx: Context,
        query: Annotated[
            str,
            Field(
                description="A name or address, e.g. 'Time Out Market Lisbon'; or 'lat,lon' to see what is at a point"
            ),
        ],
        limit: Annotated[int, Field(ge=1, le=20)] = 8,
    ) -> dict:
        """Search the map for real-world places. Results are NOT saved. To save one, call
        check_duplicate_locations and then save_place_as_location (or create_location) with the result's
        name, latitude, longitude and place_id."""
        data = await api(ctx).get("/api/places/search/", params={"q": query})
        results = [shaping.place(p) for p in data.get("results", [])[:limit]]
        return shaping.compact({"results": results, "warning": data.get("warning")})

    @mcp.tool(annotations=EXTERNAL)
    async def get_place_details(
        ctx: Context,
        place_id: Annotated[str | None, Field(description="place_id from search_places")] = None,
        name: Annotated[str | None, Field(description="Used to search again if place_id is unknown")] = None,
    ) -> dict:
        """Get more about one place from search_places: description, address, rating, website, phone."""
        d = await api(ctx).get("/api/places/details/", params={"place_id": place_id, "name": name})
        return shaping.compact(
            {
                "name": d.get("name"),
                "description": shaping.clip(d.get("description"), 1000),
                "address": d.get("formatted_address"),
                "types": d.get("types"),
                "rating": d.get("rating"),
                "review_count": d.get("review_count"),
                "website": d.get("website"),
                "phone_number": d.get("phone_number"),
                "google_maps_url": d.get("google_maps_url"),
            }
        )
