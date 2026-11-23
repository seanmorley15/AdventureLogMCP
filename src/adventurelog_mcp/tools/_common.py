from __future__ import annotations

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
# Creates send a client-chosen id, so repeating the call returns the same record instead of a duplicate.
CREATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# Creates that cannot be made repeat-safe (the API takes no client id).
CREATE_NEW = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
# Calls that reach an outside service (map/place search).
EXTERNAL = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

PAGE_SIZE = 25
