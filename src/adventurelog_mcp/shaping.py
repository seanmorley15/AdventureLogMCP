"""Compact shapes for AdventureLog records.

The API answers with everything the web app draws (images, owner profiles, timestamps). A model needs
ids, names, dates, places and short text, so these functions keep that and drop the rest.
"""

from __future__ import annotations

from typing import Any


def compact(value: Any) -> Any:
    """Drop None, empty strings and empty lists/dicts, recursively."""
    if isinstance(value, dict):
        out = {k: compact(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def clip(text: str | None, limit: int) -> str | None:
    if not text or len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _name(obj: Any) -> str | None:
    return obj.get("name") if isinstance(obj, dict) else None


def category_name(cat: Any) -> str | None:
    if isinstance(cat, dict):
        return cat.get("display_name") or cat.get("name")
    return cat


def visit(v: dict) -> dict:
    return compact(
        {
            "id": v.get("id"),
            "start_date": v.get("start_date"),
            "end_date": v.get("end_date"),
            "notes": clip(v.get("notes"), 500),
        }
    )


def location_brief(loc: dict) -> dict:
    """One line per location, for lists."""
    return compact(
        {
            "id": loc.get("id"),
            "name": loc.get("name"),
            "category": category_name(loc.get("category")),
            "address": loc.get("location"),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "rating": loc.get("rating"),
            "is_visited": loc.get("is_visited"),
            "collection_ids": loc.get("collections"),
        }
    )


def location_full(loc: dict) -> dict:
    return compact(
        {
            **location_brief(loc),
            "description": clip(loc.get("description"), 2000),
            "tags": loc.get("tags"),
            "link": loc.get("link"),
            "price": loc.get("price"),
            "price_currency": loc.get("price_currency"),
            "is_public": loc.get("is_public"),
            "city": _name(loc.get("city")),
            "region": _name(loc.get("region")),
            "country": _name(loc.get("country")),
            "visits": [visit(v) for v in loc.get("visits") or []],
        }
    )


def collection_brief(c: dict) -> dict:
    return compact(
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "description": clip(c.get("description"), 300),
            # The API calls a dated collection a "trip"; here it is a "plan".
            "type": "plan" if c.get("type") == "trip" else c.get("type"),
            "start_date": c.get("start_date"),
            "end_date": c.get("end_date"),
            "status": c.get("status"),
            "location_count": c.get("location_count"),
            "is_archived": c.get("is_archived") or None,
            "visibility": c.get("visibility"),
        }
    )


def lodging(x: dict) -> dict:
    return compact(
        {
            "id": x.get("id"),
            "name": x.get("name"),
            "type": x.get("type"),
            "check_in": x.get("check_in"),
            "check_out": x.get("check_out"),
            "address": x.get("location"),
            "latitude": x.get("latitude"),
            "longitude": x.get("longitude"),
            "reservation_number": x.get("reservation_number"),
            "price": x.get("price"),
            "price_currency": x.get("price_currency"),
            "link": x.get("link"),
            "description": clip(x.get("description"), 500),
        }
    )


def transportation(x: dict) -> dict:
    return compact(
        {
            "id": x.get("id"),
            "name": x.get("name"),
            "type": x.get("type"),
            "from": x.get("from_location"),
            "to": x.get("to_location"),
            "start": x.get("date"),
            "end": x.get("end_date"),
            "flight_number": x.get("flight_number"),
            "start_code": x.get("start_code"),
            "end_code": x.get("end_code"),
            "price": x.get("price"),
            "price_currency": x.get("price_currency"),
            "description": clip(x.get("description"), 500),
        }
    )


def note(x: dict) -> dict:
    return compact(
        {
            "id": x.get("id"),
            "name": x.get("name"),
            "date": x.get("date"),
            "content": clip(x.get("content"), 2000),
            "links": x.get("links"),
        }
    )


def checklist(x: dict) -> dict:
    return compact(
        {
            "id": x.get("id"),
            "name": x.get("name"),
            "date": x.get("date"),
            "items": [{"name": i.get("name"), "is_checked": i.get("is_checked")} for i in x.get("items") or []],
        }
    )


def collection_full(c: dict) -> dict:
    return compact(
        {
            **collection_brief(c),
            "day_count": c.get("day_count"),
            "timezone": c.get("timezone"),
            "link": c.get("link"),
            "locations": [location_brief(x) for x in c.get("locations") or []],
            "lodgings": [lodging(x) for x in c.get("lodging") or []],
            "transportations": [transportation(x) for x in c.get("transportations") or []],
            "notes": [note(x) for x in c.get("notes") or []],
            "checklists": [checklist(x) for x in c.get("checklists") or []],
        }
    )


def place(p: dict) -> dict:
    return compact(
        {
            "place_id": p.get("place_id"),
            "name": p.get("name"),
            "address": p.get("display_name"),
            "latitude": p.get("lat"),
            "longitude": p.get("lon"),
            "category": p.get("category") or p.get("type"),
            "rating": p.get("rating"),
            "review_count": p.get("review_count"),
            "website": p.get("website"),
            "description": clip(p.get("description"), 300),
        }
    )


def page(data: dict, shaper, page_no: int) -> dict:
    """A paginated API list, as {count, page, has_more, results}."""
    return compact(
        {
            "count": data.get("count"),
            "page": page_no,
            "has_more": bool(data.get("next")),
            "results": [shaper(x) for x in data.get("results", [])],
        }
    )


# --- day plan -------------------------------------------------------------------------------------------

_KIND_KEYS = {
    "location": "locations",
    "lodging": "lodging",
    "transportation": "transportations",
    "note": "notes",
    "checklist": "checklists",
}


def _names_by_kind(collection: dict) -> dict[str, dict[str, str]]:
    """{kind: {record id: name}} from a collection's contents (plan items only carry ids)."""
    return {
        kind: {r["id"]: r.get("name") for r in collection.get(key) or [] if r.get("id")}
        for kind, key in _KIND_KEYS.items()
    }


def _clock(t: str | None) -> str | None:
    return t[:5] if t else t  # "10:00:00" -> "10:00"


def plan_item(item: dict, names: dict[str, dict[str, str]]) -> dict:
    kind = item.get("content_type")
    return compact(
        {
            "item_id": item.get("id"),
            "kind": kind,
            "name": names.get(kind, {}).get(item.get("object_id")),
            "object_id": item.get("object_id"),
            "start_time": _clock(item.get("start_time")),
            "end_time": _clock(item.get("end_time")),
            "timezone": item.get("timezone"),
            "optional": item.get("is_optional") or None,
            "through_day": item.get("span_end_index"),
            "visit_logged": bool(item.get("logged_visit")) or None,
        }
    )


def day_plan(plan: dict, collection: dict) -> dict:
    """The plan as a person reads it: numbered days with named items, Ideas, trip-wide items, and what is
    in the collection but not placed yet. Empty lists and sections are left out."""
    names = _names_by_kind(collection)
    items = sorted(plan.get("itinerary") or [], key=lambda i: i.get("order") or 0)
    by_day: dict[int, list[dict]] = {}
    ideas, trip_wide = [], []
    placed: set[str] = set()
    for it in items:
        placed.add(it.get("object_id"))
        shaped = plan_item(it, names)
        if it.get("is_global"):
            trip_wide.append(shaped)
        elif it.get("day_index") is None:
            ideas.append(shaped)
        else:
            by_day.setdefault(it["day_index"], []).append(shaped)
    days = [
        {
            **compact(
                {
                    "day": d.get("index"),
                    "date": d.get("date"),
                    "name": d.get("name"),
                    "description": clip(d.get("description"), 300),
                }
            ),
            "items": by_day.get(d.get("index"), []),
        }
        for d in sorted(plan.get("itinerary_days") or [], key=lambda d: d.get("index") or 0)
    ]
    unplaced = {
        kind: [{"id": rid, "name": name} for rid, name in recs.items() if rid not in placed]
        for kind, recs in names.items()
    }
    c = plan.get("collection") or {}
    return compact(
        {
            "collection": {
                "id": c.get("id") or collection.get("id"),
                "name": collection.get("name"),
                "start_date": c.get("start_date"),
                "end_date": c.get("end_date"),
                "day_count": c.get("day_count"),
                "timezone": c.get("timezone"),
            },
            "days": days,
            "ideas": ideas,
            "trip_wide": trip_wide,
            "not_scheduled_yet": unplaced,
        }
    )


def recommendation(r: dict) -> dict:
    return compact(
        {
            "place_id": r.get("place_id"),
            "name": r.get("name"),
            "description": clip(r.get("description"), 200),
            "address": r.get("address"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "distance_km": r.get("distance_km"),
            "rating": r.get("rating"),
            "review_count": r.get("review_count"),
            "price_level": r.get("price_level"),
            "type": r.get("primary_type"),
            "open_now": r.get("is_open_now"),
            "website": r.get("website"),
        }
    )


# --- world travel ---------------------------------------------------------------------------------------


def country(c: dict) -> dict:
    return compact(
        {
            "code": c.get("country_code"),
            "name": c.get("name"),
            "capital": c.get("capital"),
            "subregion": c.get("subregion"),
            "regions": c.get("num_regions"),
            "visited_regions": c.get("num_visits"),
        }
    )


def region(r: dict, visited: bool | None = None) -> dict:
    return compact(
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "cities": r.get("num_cities"),
            "visited": visited,
            "territory_of": r.get("territory_country_code"),
        }
    )


def city(c: dict, visited: bool | None = None) -> dict:
    return compact({"id": c.get("id"), "name": c.get("name"), "region": c.get("region_name"), "visited": visited})
