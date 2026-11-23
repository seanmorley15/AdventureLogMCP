"""Prompt templates: reusable starting points that tell the model which tools to use, and in what order."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer


def register(mcp: MCPServer) -> None:
    @mcp.prompt(title="Plan a collection")
    def plan_collection(destination: str, dates: str = "", interests: str = "", travelers: str = "") -> str:
        """Build a dated plan for a destination: a collection with locations, a stay, travel and a day-by-day plan."""
        return f"""Plan a collection in AdventureLog for {destination}.
Dates: {dates or "not decided; ask me, or propose a sensible length"}.
Interests: {interests or "general sightseeing, food and a few local favourites"}.
Travelers: {travelers or "not specified"}.

Work in this order and tell me what you did at each step:
1. search for existing collections and locations about {destination} so you reuse what I already saved.
2. create_collection as a plan (type "plan") with the dates, then ask me before continuing if anything big is unclear.
3. Find places with search_places and recommend_nearby; run check_duplicate_locations, then save the good ones with
   save_place_as_location (collection_id set). Give each a Markdown description of the place itself only,
   with nothing about this plan, its days or dates. Prefer a realistic number per day, close together.
4. Add create_lodging, create_transportation, a create_note with practical tips and a create_checklist (packing).
5. Use get_day_plan, then schedule_item (with start_time) to fill each day; keep days balanced and group nearby
   locations. Leave extras in Ideas.
6. Finish with get_day_plan and summarise the plan day by day, and what is still not scheduled."""

    @mcp.prompt(title="Collection briefing")
    def collection_briefing(collection: str) -> str:
        """Summarise a collection: what is planned, what is booked, and what is missing."""
        return f"""Give me a briefing for my AdventureLog collection "{collection}".
Find it with search or list_collections, then read it with get_collection and (if it has dates) get_day_plan.
Cover: dates and length; each day's plan; where I am staying and how I travel (with times and reservation
numbers); notes and checklist items still unchecked; and anything not scheduled yet.
Point out gaps (days with nothing, no stay for some nights, no way to get there), but do not change anything."""

    @mcp.prompt(title="Year in review")
    def year_in_review(year: str) -> str:
        """Summarise a year of travel from visits, countries, regions and cities."""
        return f"""Write a travel year in review for {year} from my AdventureLog data.
Use list_locations (is_visited true, ordering "-date") and get_location for the visits dated in {year}; then
get_travel_stats and list_countries (visited_only) for the totals. Group by collection or region, name my highest-rated
places, and mention new countries or regions. Say clearly when something is a total across all years rather than
just {year}. Do not change anything."""
