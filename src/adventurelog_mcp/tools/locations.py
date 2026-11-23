"""Locations: places the user has been to or wants to go, with their visits, categories and tags."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from .. import shaping
from ..auth import api
from ._common import CATEGORY, CATEGORY_ICON, CREATE, CREATE_NEW, DESCRIBE, PAGE_SIZE, READ_ONLY, resolve_category


class VisitInput(BaseModel):
    start_date: Annotated[str | None, Field(description="ISO date or datetime the visit started, e.g. 2026-06-03")] = (
        None
    )
    end_date: Annotated[str | None, Field(description="ISO date or datetime the visit ended")] = None
    notes: str | None = None


async def _existing_location(a, name: str, latitude: float, longitude: float, address: str | None) -> dict | None:
    """The user's own saved location that is clearly this same place: a similar name AND close by.
    Merely being near a different place is not enough, so neighbours are never merged. Best effort."""
    try:
        data = await a.post(
            "/api/locations/check-duplicates/",
            json={"name": name, "latitude": latitude, "longitude": longitude, "location": address},
        )
    except ToolError:
        return None
    for m in data.get("matches", []):
        reasons = m.get("reasons") or []
        if "similar_name" in reasons and (m.get("score") or 0) >= 0.9:
            return m
    return None


async def _reuse(a, match: dict, collection_id: str | None, visits: list | None = None) -> dict:
    """Return the existing location (added to the collection, with any visits, when asked) instead of a copy."""
    if collection_id:
        await a.post(f"/api/locations/{match['id']}/collections/{collection_id}/")
    for v in visits or []:
        fields = {k: v.get(k) for k in ("start_date", "end_date", "notes")}
        await a.post("/api/visits/", json=a.create_body("visit", location=match["id"], **fields))
    data = await a.get(f"/api/locations/{match['id']}/")
    out = shaping.location_full(data)
    out["reused_existing"] = True
    if collection_id:
        out["added_to_collection"] = collection_id
    return out


async def _photos_for_place(a, place_id: str, name: str, address: str | None) -> list[str] | None:
    """Best effort: the place's picture addresses, found by searching again. Never blocks the save."""
    try:
        found = await a.get("/api/places/search/", params={"q": ", ".join(filter(None, [name, address]))})
    except ToolError:
        return None
    for p in found.get("results", []):
        if p.get("place_id") == place_id:
            return (p.get("photos") or [])[:3] or None
    return None


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
        address: Annotated[
            str | None,
            Field(description='Only if the user gave one. Leave it out and AdventureLog fills in "City, Region, US"'),
        ] = None,
        description: Annotated[str | None, Field(description=DESCRIBE)] = None,
        category: Annotated[
            str | None,
            Field(description=CATEGORY),
        ] = None,
        category_icon: Annotated[str | None, Field(description=CATEGORY_ICON)] = None,
        tags: list[str] | None = None,
        rating: Annotated[float | None, Field(ge=0, le=5)] = None,
        link: str | None = None,
        price: str | None = None,
        is_public: bool = False,
        collection_id: Annotated[str | None, Field(description="Put it in this collection right away")] = None,
        visits: Annotated[
            list[VisitInput] | None, Field(description="Past or planned visits. Omit for a wishlist location")
        ] = None,
        allow_duplicate: Annotated[
            bool, Field(description="Only if the user wants a second copy of a place they already saved")
        ] = False,
    ) -> dict:
        """Save a new location. Leave `address` out and AdventureLog
        fills it in as "City, Region, US". Coordinates are what put it on the map; if you only have a name, use
        search_places first to get them. If the user already has this place saved it is reused (returned with
        `reused_existing: true`, and added to `collection_id` and given the `visits`) instead of duplicated.
        Safe to repeat: the identical call returns the existing location."""
        a = api(ctx)
        if not allow_duplicate and (match := await _existing_location(a, name, latitude, longitude, address)):
            return await _reuse(a, match, collection_id, [v.model_dump(exclude_none=True) for v in visits or []])
        fields: dict[str, Any] = {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "location": address,
            "description": description,
            "category": await resolve_category(a, category, category_icon) if category else None,
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
            str | None,
            Field(description=DESCRIBE + " It is kept instead of the description imported for the place."),
        ] = None,
        website: str | None = None,
        rating: Annotated[float | None, Field(ge=0, le=5)] = None,
        category: Annotated[
            str | None,
            Field(description=CATEGORY),
        ] = None,
        category_icon: Annotated[str | None, Field(description=CATEGORY_ICON)] = None,
        collection_id: Annotated[str | None, Field(description="Add it to this collection")] = None,
        itinerary_date: Annotated[
            str | None, Field(description="YYYY-MM-DD: also put it on this day of a dated collection")
        ] = None,
        photos: Annotated[
            list[str] | None,
            Field(description="`photos` addresses from search_places results, to import as the location's pictures"),
        ] = None,
        allow_duplicate: Annotated[
            bool, Field(description="Only if the user wants a second copy of a place they already saved")
        ] = False,
    ) -> dict:
        """Save a result from search_places as a location, the way the map's "add" button does (imports details
        and pictures: the place's own photos are fetched automatically when `photos` is left out).
        If the user already saved this
        place it is reused (`reused_existing: true`) and added to the collection instead of duplicated.
        To add other pictures afterwards use find_images and add_images."""
        a = api(ctx)
        if not allow_duplicate and (match := await _existing_location(a, name, latitude, longitude, address)):
            out = await _reuse(a, match, collection_id)
            if itinerary_date:
                out["note"] = "Already saved, so it was reused. Use schedule_item to put it on a day."
            return out
        if place_id and not photos:
            photos = await _photos_for_place(a, place_id, name, address)
        body = {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "place_id": place_id,
            "location": address,
            "description": description,
            "website": website,
            "rating": rating,
            "category": await resolve_category(a, category, category_icon) if category else None,
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
        # The API only reports photos that failed to import; the rest are in `images`.
        failed = (data.get("quick_add_image_import") or {}).get("failed_count")
        if failed:
            shaped["photos_failed"] = failed
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
