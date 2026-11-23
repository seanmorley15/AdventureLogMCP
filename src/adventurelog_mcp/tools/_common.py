from __future__ import annotations

import re

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
# Creates send a client-chosen id, so repeating the call returns the same record instead of a duplicate.
CREATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# Creates that cannot be made repeat-safe (the API takes no client id).
CREATE_NEW = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
# Calls that reach an outside service (map/place search).
EXTERNAL = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

PAGE_SIZE = 25


def category_fields(raw: str) -> dict:
    """A category as AdventureLog wants it: an object, which uses the user's category of that name or creates one.

    A bare string would be read as a category *id* and rejected when it is a name. The name is lower-case with
    spaces, like categories made in the web app ("Historical Place" and "historical_place" are the same one).
    """
    cleaned = re.sub(r"[\s_]+", " ", raw.strip())
    return {"name": cleaned.lower(), "display_name": cleaned if cleaned != cleaned.lower() else cleaned.title()}


# What a location's description should say. The location outlives any one collection or plan.
DESCRIBE = (
    "1-3 sentences about the place itself: what it is, where, and why it is worth visiting. "
    "Keep it general and timeless. Do not mention the collection, the plan, the dates or the day it is scheduled for "
    "(put those in a note or the day plan)."
)
