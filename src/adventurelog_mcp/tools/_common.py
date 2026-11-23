from __future__ import annotations

import difflib
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
    "Markdown about the place itself, as it would appear in a guidebook: what it is, its history or character, "
    "what to see or do there, and practical facts that always hold (setting, best season, what it is known for). "
    "Use short paragraphs or a few bullet points. It must contain NOTHING about a trip, collection, plan, "
    "itinerary, day, date, schedule or who is going; those belong in a note or the day plan."
)


def _stem(word: str) -> str:
    for suffix in ("ies", "es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def _key(text: str) -> str:
    return " ".join(sorted(_stem(w) for w in re.sub(r"[^a-z0-9]+", " ", text.lower()).split()))


async def resolve_category(a, raw: str) -> dict:
    """Reuse one of the user's categories when it is the same thing ("Hiking Areas" for "hiking area",
    "museum" for "Museums"), otherwise create a new one by name. Never fails the call: if the categories cannot
    be read, the name is simply sent and AdventureLog reuses or creates it."""
    wanted = _key(raw)
    try:
        existing = await a.get("/api/categories/")
    except Exception:
        return category_fields(raw)
    names = [(c, _key(c.get("name") or ""), _key(c.get("display_name") or "")) for c in existing or []]
    for c, by_name, by_display in names:
        if wanted in (by_name, by_display):
            return {"name": c["name"], "display_name": c.get("display_name") or c["name"]}
    close = difflib.get_close_matches(wanted, [k for _, k, _ in names if k], n=1, cutoff=0.9)
    if close:
        c = next(c for c, k, _ in names if k == close[0])
        return {"name": c["name"], "display_name": c.get("display_name") or c["name"]}
    return category_fields(raw)


CATEGORY = (
    "What kind of place it is, e.g. Museum, Hiking Area, Restaurant. An existing category of the same kind is "
    "reused; a new one is created only if none fits."
)
