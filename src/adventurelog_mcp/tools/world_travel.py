"""World travel: countries, regions and cities the user has visited, and travel totals."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import shaping
from ..auth import api
from ._common import READ_ONLY

MARK = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
UNMARK = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)

CODE = Field(min_length=2, max_length=2, description="ISO country code, e.g. PT")


def _visited_ids(rows: list[dict], key: str) -> set[str]:
    """Ids from /visited-regions or /visited-cities (each row names the region/city it marks)."""
    out = set()
    for r in rows:
        v = r.get(key)
        out.add(v.get("id") if isinstance(v, dict) else v)
    return out


def _filter(items: list[dict], query: str | None) -> list[dict]:
    if not query:
        return items
    q = query.casefold()
    return [i for i in items if q in (i.get("name") or "").casefold() or q in (i.get("native_name") or "").casefold()]


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_countries(
        ctx: Context,
        visited_only: Annotated[bool, Field(description="Only countries with at least one visited region")] = False,
        query: Annotated[str | None, Field(description="Part of a country name")] = None,
        limit: Annotated[int, Field(ge=1, le=300)] = 60,
    ) -> dict:
        """List countries with how many of their regions the user has visited. Reference data for all
        250 countries, so filter with `visited_only` or `query`."""
        rows = _filter(await api(ctx).get("/api/countries/"), query)
        if visited_only:
            rows = [r for r in rows if r.get("num_visits")]
        return {"count": len(rows), "countries": [shaping.country(r) for r in rows[:limit]]}

    @mcp.tool(annotations=READ_ONLY)
    async def get_country(ctx: Context, country_code: Annotated[str, CODE]) -> dict:
        """One country: capital, subregion, and visited regions out of the total."""
        return shaping.country(await api(ctx).get(f"/api/countries/{country_code.upper()}/"))

    @mcp.tool(annotations=READ_ONLY)
    async def list_regions(
        ctx: Context,
        country_code: Annotated[str, CODE],
        visited: Annotated[bool | None, Field(description="true: only visited. false: only not visited yet")] = None,
        query: Annotated[str | None, Field(description="Part of a region name")] = None,
    ) -> dict:
        """List a country's regions (states, provinces...) with whether the user has visited each. Region ids
        are what mark_region_visited and list_cities take."""
        a = api(ctx)
        code = country_code.upper()
        regions = await a.get(f"/api/countries/{code}/regions/")
        done = _visited_ids(await a.get("/api/visited-regions/", params={"country": code}), "region")
        rows = [shaping.region(r, r.get("id") in done) for r in _filter(regions, query)]
        if visited is not None:
            rows = [r for r in rows if bool(r.get("visited")) == visited]
        return {"count": len(rows), "regions": rows}

    @mcp.tool(annotations=READ_ONLY)
    async def list_cities(
        ctx: Context,
        region_id: Annotated[str, Field(description="Region id from list_regions, e.g. PT-11")],
        visited: bool | None = None,
        query: Annotated[str | None, Field(description="Part of a city name")] = None,
        limit: Annotated[int, Field(ge=1, le=300)] = 60,
    ) -> dict:
        """List a region's cities with whether the user has visited each."""
        a = api(ctx)
        cities = await a.get(f"/api/regions/{region_id}/cities/")
        done = _visited_ids(await a.get("/api/visited-cities/", params={"region": region_id}), "city")
        rows = [shaping.city(c, c.get("id") in done) for c in _filter(cities, query)]
        if visited is not None:
            rows = [r for r in rows if bool(r.get("visited")) == visited]
        return {"count": len(rows), "cities": rows[:limit]}

    @mcp.tool(annotations=MARK)
    async def mark_region_visited(ctx: Context, region_id: Annotated[str, Field(description="e.g. PT-11")]) -> dict:
        """Mark a region as visited. Visiting a saved location in a region marks it automatically."""
        await api(ctx).post("/api/visited-regions/", json={"region": region_id})
        return {"region_id": region_id, "visited": True}

    @mcp.tool(annotations=UNMARK)
    async def unmark_region_visited(ctx: Context, region_id: str) -> dict:
        """Remove a region's visited mark. Locations and visits are not changed."""
        await api(ctx).delete(f"/api/visited-regions/{region_id}/")
        return {"region_id": region_id, "visited": False}

    @mcp.tool(annotations=MARK)
    async def mark_city_visited(ctx: Context, city_id: str) -> dict:
        """Mark a city as visited. Its region is marked visited too."""
        await api(ctx).post("/api/visited-cities/", json={"city": city_id})
        return {"city_id": city_id, "visited": True}

    @mcp.tool(annotations=UNMARK)
    async def unmark_city_visited(ctx: Context, city_id: str) -> dict:
        """Remove a city's visited mark. Locations and visits are not changed."""
        await api(ctx).delete(f"/api/visited-cities/{city_id}/")
        return {"city_id": city_id, "visited": False}

    @mcp.tool(annotations=MARK)
    async def sync_visited_regions(ctx: Context) -> dict:
        """Mark the region and city of every location the user has visited as visited, and report the new ones.
        Useful after adding many locations."""
        return shaping.compact(await api(ctx).post("/api/visited-regions/sync/"))

    @mcp.tool(annotations=READ_ONLY)
    async def get_travel_stats(ctx: Context) -> dict:
        """Travel totals: locations (and how many visited), collections, and countries, regions and cities
        visited out of all that exist, plus activity totals."""
        a = api(ctx)
        username = (await a.get("/api/account/"))["user"]["username"]
        s = await a.get(f"/api/users/{username}/stats/")
        return shaping.compact(
            {
                "locations": s.get("location_count"),
                "visited_locations": s.get("visited_location_count"),
                "collections": s.get("trips_count"),
                "countries": {"visited": s.get("visited_country_count"), "total": s.get("total_countries")},
                "regions": {"visited": s.get("visited_region_count"), "total": s.get("total_regions")},
                "cities": {"visited": s.get("visited_city_count"), "total": s.get("total_cities")},
                "activities": s.get("activity_count"),
                "activity_distance_m": s.get("activity_distance"),
            }
        )
