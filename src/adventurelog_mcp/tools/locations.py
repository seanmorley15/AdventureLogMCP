"""Locations: places the user has been to or wants to go, with their visits, categories and tags."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from pydantic import BaseModel, Field

from .. import shaping
from ..auth import api
from ._common import CREATE, CREATE_NEW, PAGE_SIZE, READ_ONLY, category_fields


class VisitInput(BaseModel):
    start_date: Annotated[str | None, Field(description="ISO date or datetime the visit started, e.g. 2026-06-03")] = (
        None
    )
    end_date: Annotated[str | None, Field(description="ISO date or datetime the visit ended")] = None
    notes: str | None = None


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def search(
        ctx: Context,
        query: Annotated[str, Field(description="Words to look for (2+ characters each)")],
        types: Annotated[
            str | None, Field(description="Comma-separated kinds, e.g. 'location,collection'. Default: all")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> dict:
        """Search everything the user owns (locations, collections, ...) by name. Use this before creating
        something, to find out whether it already exists. Returns each hit with its kind and id."""
        data = await api(ctx).get("/api/search/", params={"q": query, "types": types, "limit": limit})
        hits = [
            shaping.compact(
                {"type": h.get("type"), "id": h.get("id"), "name": h.get("title"), "detail": h.get("subtitle")}
            )
            for h in data.get("results", [])
        ]
        facets = {k: v for k, v in (data.get("facets") or {}).items() if v}
        return {"count": data.get("count"), "results": hits, "matches_by_kind": facets}

    @mcp.tool(annotations=READ_ONLY)
    async def list_locations(
        ctx: Context,
        category: Annotated[str | None, Field(description="Comma-separated category names")] = None,
        is_visited: Annotated[bool | None, Field(description="true: has a past visit. false: wishlist")] = None,
        in_collection: Annotated[
            bool | None, Field(description="true: in at least one collection. false: in none")
        ] = None,
        ordering: Annotated[
            str | None, Field(description="'name', 'date' (latest visit), 'rating', or prefix '-' to reverse")
        ] = None,
        page: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=100)] = PAGE_SIZE,
    ) -> dict:
        """List the user's saved locations, one short entry each. Use get_location for full details."""
        data = await api(ctx).get(
            "/api/locations/",
            params={
                "category": category,
                "is_visited": _bool(is_visited),
                "in_collection": _bool(in_collection),
                "ordering": ordering,
                "page": page,
                "page_size": page_size,
            },
        )
        return shaping.page(data, shaping.location_brief, page)

    @mcp.tool(annotations=READ_ONLY)
    async def get_location(ctx: Context, location_id: str) -> dict:
        """Get one location in full: description, address, coordinates, tags, rating, visits and the ids of
        the collections it is in. `version` can be passed to update_location to detect edits made meanwhile."""
        data, etag = await api(ctx).get(f"/api/locations/{location_id}/", with_etag=True)
        return shaping.versioned(shaping.location_full(data), etag)

    @mcp.tool(annotations=READ_ONLY)
    async def check_duplicate_locations(
        ctx: Context,
        name: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        address: str | None = None,
    ) -> dict:
        """Find saved locations that look like the one you are about to create (similar name, nearby).
        Call this before create_location or save_place_as_location; if a match is right, use it instead."""
        data = await api(ctx).post(
            "/api/locations/check-duplicates/",
            json={"name": name, "latitude": latitude, "longitude": longitude, "location": address},
        )
        matches = [
            shaping.compact(
                {
                    "id": m.get("id"),
                    "name": m.get("name"),
                    "address": m.get("location"),
                    "distance_meters": m.get("distance_meters"),
                    "is_visited": m.get("is_visited"),
                    "reasons": m.get("reasons"),
                }
            )
            for m in data.get("matches", [])
        ]
        return {"matches": matches}

    @mcp.tool(annotations=CREATE)
    async def create_location(
        ctx: Context,
        name: str,
        latitude: Annotated[float | None, Field(ge=-90, le=90)] = None,
        longitude: Annotated[float | None, Field(ge=-180, le=180)] = None,
        address: Annotated[str | None, Field(description="Human-readable address or area")] = None,
        description: str | None = None,
        category: Annotated[str | None, Field(description="Category name; see list_categories. Created if new")] = None,
        tags: list[str] | None = None,
        rating: Annotated[float | None, Field(ge=0, le=5)] = None,
        link: str | None = None,
        price: str | None = None,
        is_public: bool = False,
        collection_id: Annotated[str | None, Field(description="Put it in this collection right away")] = None,
        visits: Annotated[
            list[VisitInput] | None, Field(description="Past or planned visits. Omit for a wishlist location")
        ] = None,
    ) -> dict:
        """Save a new location. Coordinates are what put it on the map; if you only have a name, use
        search_places first to get them. Safe to repeat: the identical call returns the existing location."""
        a = api(ctx)
        fields: dict[str, Any] = {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "location": address,
            "description": description,
            "category": category_fields(category) if category else None,
            "tags": tags,
            "rating": rating,
            "link": link,
            "price": price,
            "is_public": is_public,
            "collections": [collection_id] if collection_id else None,
            "visits": [v.model_dump(exclude_none=True) for v in visits] if visits else None,
        }
        data, etag = await a.post("/api/locations/", json=a.create_body("location", **fields), with_etag=True)
        return shaping.versioned(shaping.location_full(data), etag)

    @mcp.tool(annotations=CREATE_NEW)
    async def save_place_as_location(
        ctx: Context,
        name: str,
        latitude: Annotated[float, Field(ge=-90, le=90)],
        longitude: Annotated[float, Field(ge=-180, le=180)],
        place_id: Annotated[
            str | None, Field(description="place_id from search_places; lets AdventureLog import details")
        ] = None,
        address: str | None = None,
        description: Annotated[
            str | None, Field(description="Your own text. It is kept instead of the description imported for the place")
        ] = None,
        website: str | None = None,
        rating: Annotated[float | None, Field(ge=0, le=5)] = None,
        category: Annotated[
            str | None, Field(description="Category name; created if the user has none by that name")
        ] = None,
        collection_id: Annotated[str | None, Field(description="Add it to this collection")] = None,
        itinerary_date: Annotated[
            str | None, Field(description="YYYY-MM-DD: also put it on this day of a dated collection")
        ] = None,
        photos: Annotated[
            list[str] | None,
            Field(description="`photos` addresses from search_places results, to import as the location's pictures"),
        ] = None,
    ) -> dict:
        """Save a result from search_places as a location, the way the map's "add" button does (imports details
        and, when `photos` are given, pictures). Not safe to repeat: run check_duplicate_locations first.
        To add other pictures afterwards use find_images and add_images."""
        a = api(ctx)
        body = {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "place_id": place_id,
            "location": address,
            "description": description,
            "website": website,
            "rating": rating,
            "category": category_fields(category) if category else None,
            "collection": collection_id,
            "itinerary_date": itinerary_date,
            "photos": photos,
        }
        data = await a.post("/api/locations/quick-add/", json={k: v for k, v in body.items() if v is not None})
        # AdventureLog replaces the caller's description with the one it fetched for the place_id. The caller's
        # own words should win, so write them back.
        if description and data.get("description") != description:
            data = {**data, **await a.patch(f"/api/locations/{data['id']}/", json={"description": description})}
        shaped = shaping.location_full(data)
        imported = data.get("quick_add_image_import")
        if isinstance(imported, dict):
            shaped["photos_imported"] = imported.get("created_count", imported.get("imported"))
        return shaping.compact(shaped)

    @mcp.tool(annotations=CREATE)
    async def log_visit(
        ctx: Context,
        location_id: str,
        start_date: Annotated[str | None, Field(description="ISO date/datetime, e.g. 2026-06-03")] = None,
        end_date: str | None = None,
        notes: str | None = None,
    ) -> dict:
        """Record that the user visited (or will visit) an existing location.

        Repeating the identical call does not add a second visit."""
        a = api(ctx)
        body = a.create_body("visit", location=location_id, start_date=start_date, end_date=end_date, notes=notes)
        return shaping.visit(await a.post("/api/visits/", json=body))

    @mcp.tool(annotations=READ_ONLY)
    async def list_categories(ctx: Context) -> dict:
        """List location categories with how many locations each holds. Pass a name to create_location."""
        data = await api(ctx).get("/api/categories/")
        return {
            "categories": [
                {"name": c.get("name"), "display_name": c.get("display_name"), "locations": c.get("num_locations")}
                for c in data
            ]
        }

    @mcp.tool(annotations=READ_ONLY)
    async def list_tags(ctx: Context) -> dict:
        """List the tags the user has used on locations."""
        data = await api(ctx).get("/api/tags/")
        return {"tags": sorted({t for group in data for t in (group if isinstance(group, list) else [group])})}


def _bool(v: bool | None) -> str | None:
    return None if v is None else str(v).lower()
