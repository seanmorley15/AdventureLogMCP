"""Pictures: find them, attach them to records, pick the cover. Files already on a record can be listed."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .. import shaping
from ..auth import api
from ._common import CREATE_NEW, EXTERNAL, READ_ONLY

Kind = Literal["location", "lodging", "transportation", "note", "visit"]
_PATHS = {
    "location": "locations",
    "lodging": "lodgings",
    "transportation": "transportations",
    "note": "notes",
    "visit": "visits",
}


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=EXTERNAL)
    async def find_images(
        ctx: Context,
        query: Annotated[str, Field(description="What to find pictures of, e.g. 'Seneca Rocks West Virginia'")],
    ) -> dict:
        """Find freely licensed pictures (Wikipedia) of a place. Nothing is saved: pass chosen `url`s to
        add_images. Pictures from search_places results (`photos`) can be passed to add_images too."""
        data = await api(ctx).get("/api/places/images/", params={"name": query})
        images = [
            shaping.compact(
                {
                    "url": i.get("source"),
                    "title": i.get("title"),
                    "width": i.get("width"),
                    "height": i.get("height"),
                }
            )
            for i in data.get("images", [])
        ]
        return {"images": images}

    @mcp.tool(annotations=CREATE_NEW)
    async def add_images(
        ctx: Context,
        kind: Annotated[Kind, Field(description="What kind of record the pictures go on")],
        record_id: Annotated[str, Field(description="The record's id")],
        urls: Annotated[
            list[str],
            Field(min_length=1, max_length=10, description="Picture addresses from find_images or search_places"),
        ],
    ) -> dict:
        """Download pictures and attach them to a location, lodging, transportation, note or visit. The first
        picture on a record becomes its cover. Each address gets its own result, so some can fail while
        others succeed (sites that block downloads fail; place-search `photos` work reliably)."""
        source = "google" if all(u.startswith("/api/places/photo/") for u in urls) else None
        body = {"content_type": kind, "object_id": record_id, "urls": urls}
        if source:
            body["source"] = source
        try:
            data = await api(ctx).post("/api/images/import-from-urls/", json=body)
        except ToolError as e:
            raise ToolError(f"No picture could be added. {e}") from e
        results = [
            shaping.compact({"url": r.get("url"), "status": r.get("status"), "error": r.get("error")})
            for r in data.get("results", [])
        ]
        for r in results:
            r["url"] = shaping.clip(r.get("url"), 120)
        return {
            "added": data.get("created_count"),
            "requested": data.get("requested_count"),
            "images": [shaping.image(i) for i in data.get("created", [])],
            "results": results,
        }

    @mcp.tool(annotations=READ_ONLY)
    async def list_images(
        ctx: Context,
        kind: Annotated[Kind, Field(description="What kind of record")],
        record_id: Annotated[str, Field(description="The record's id")],
    ) -> dict:
        """List a record's pictures and files (the cover is marked `is_primary`)."""
        d = await api(ctx).get(f"/api/{_PATHS[kind]}/{record_id}/")
        return shaping.compact(
            {
                "images": [shaping.image(i) for i in d.get("images") or []],
                "attachments": [shaping.attachment(x) for x in d.get("attachments") or []],
            }
        )

    @mcp.tool(annotations=CREATE_NEW)
    async def set_primary_image(
        ctx: Context, image_id: Annotated[str, Field(description="Picture id from list_images")]
    ) -> dict:
        """Make a picture the cover of its record."""
        try:
            d = await api(ctx).post(f"/api/images/{image_id}/toggle-primary/")
        except ToolError as e:
            if "already_primary" in str(e):
                return {"id": image_id, "is_primary": True}
            raise
        return shaping.image(d)
