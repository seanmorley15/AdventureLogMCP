"""Deleting records. These tools are only registered when the server runs with MCP_ALLOW_DESTRUCTIVE=true."""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from ..auth import api

DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


def register(mcp: MCPServer) -> None:
    async def _delete(ctx: Context, path: str, kind: str, record_id: str) -> dict:
        await api(ctx).delete(path)
        return {"deleted": True, "kind": kind, "id": record_id}

    @mcp.tool(annotations=DELETE)
    async def delete_location(ctx: Context, location_id: str) -> dict:
        """Permanently delete a saved location, with its visits, photos and plan entries. Cannot be undone.
        To only take it out of a collection use remove_location_from_collection."""
        return await _delete(ctx, f"/api/locations/{location_id}/", "location", location_id)

    @mcp.tool(annotations=DELETE)
    async def delete_collection(ctx: Context, collection_id: str) -> dict:
        """Permanently delete a collection together with its lodgings, transportations, notes, checklists and
        day plan. Its locations are NOT deleted; they just leave the collection. Cannot be undone."""
        return await _delete(ctx, f"/api/collections/{collection_id}/", "collection", collection_id)

    @mcp.tool(annotations=DELETE)
    async def delete_lodging(ctx: Context, lodging_id: str) -> dict:
        """Permanently delete a lodging. Cannot be undone."""
        return await _delete(ctx, f"/api/lodgings/{lodging_id}/", "lodging", lodging_id)

    @mcp.tool(annotations=DELETE)
    async def delete_transportation(ctx: Context, transportation_id: str) -> dict:
        """Permanently delete a transportation. Cannot be undone."""
        return await _delete(ctx, f"/api/transportations/{transportation_id}/", "transportation", transportation_id)

    @mcp.tool(annotations=DELETE)
    async def delete_note(ctx: Context, note_id: str) -> dict:
        """Permanently delete a note. Cannot be undone."""
        return await _delete(ctx, f"/api/notes/{note_id}/", "note", note_id)

    @mcp.tool(annotations=DELETE)
    async def delete_checklist(ctx: Context, checklist_id: str) -> dict:
        """Permanently delete a checklist and its items. Cannot be undone."""
        return await _delete(ctx, f"/api/checklists/{checklist_id}/", "checklist", checklist_id)

    @mcp.tool(annotations=DELETE)
    async def delete_visit(ctx: Context, visit_id: str) -> dict:
        """Permanently delete one visit of a location. Cannot be undone."""
        return await _delete(ctx, f"/api/visits/{visit_id}/", "visit", visit_id)
