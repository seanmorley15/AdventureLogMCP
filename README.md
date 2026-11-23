# AdventureLog MCP

An [MCP](https://modelcontextprotocol.io) server that lets AI assistants work with your
[AdventureLog](https://github.com/seanmorley15/AdventureLog): create **locations** and **collections**
(folders or dated plans), and fill collections with lodgings, transportations, notes and checklists.

It talks to AdventureLog's public REST API with **your own API key**, so it works with any AdventureLog server
and stores nothing.

## What it can do

Words used throughout: a **location** is a saved place, a **collection** is a folder of locations or a dated
**plan** (with lodgings, transportations, notes and checklists), and a **place** is a map search result that is not
saved yet.

| Area | Tools |
| --- | --- |
| Connection | `whoami` |
| Find | `search`, `list_locations`, `get_location`, `list_collections`, `get_collection`, `list_categories`, `list_tags` |
| Look up places | `search_places`, `get_place_details`, `check_duplicate_locations` |
| Create locations | `create_location`, `save_place_as_location`, `log_visit` |
| Create collections and what is in them | `create_collection`, `add_location_to_collection`, `remove_location_from_collection`, `create_lodging`, `create_transportation`, `create_note`, `create_checklist` |
| Plan the days of a dated collection | `get_day_plan`, `schedule_item`, `move_plan_item`, `order_day_items`, `remove_plan_item`, `set_day_details`, `set_plan_length`, `shift_plan_dates`, `recommend_nearby` |
| World travel | `list_countries`, `get_country`, `list_regions`, `list_cities`, `mark_region_visited`, `unmark_region_visited`, `mark_city_visited`, `unmark_city_visited`, `sync_visited_regions`, `get_travel_stats` |

Creating is repeat-safe: the record's id is derived from who is asking and exactly what they asked for, so an
identical repeated call returns the existing record. `get_day_plan` shows each day's named items, Ideas (in the collection, no day yet), plan-wide items and what is
not scheduled yet. `schedule_item` is repeat-safe and moves an Ideas item onto a day instead of duplicating it.
Changing things: `update_location`, `update_collection`, `update_lodging`, `update_transportation`,
`update_note`, `update_checklist`, `update_visit` (only the fields you pass change), and `remove_plan_item`.
`get_location` and `get_collection` return a `version`; pass it back to an update and, if the record changed
meanwhile, nothing is saved and you get its current state.

Deleting is off by default. Start the server with `MCP_ALLOW_DESTRUCTIVE=true` to add `delete_location`,
`delete_collection` (its locations are kept), `delete_lodging`, `delete_transportation`, `delete_note`,
`delete_checklist` and `delete_visit`.

Three prompts are included: `plan_collection`, `collection_briefing` and `year_in_review`.

## Connect

1. In AdventureLog, open **Settings > Security > API Keys** and create a key (`al_...`).
2. Add the server to your client.

Claude Code:

```sh
claude mcp add --transport http adventurelog http://localhost:8017/mcp \
  --header "Authorization: Bearer al_your_key"
```

Local use without Docker (stdio), from a clone of this repository:

```sh
uv sync
ADVENTURELOG_URL=http://localhost:8015 ADVENTURELOG_API_KEY=al_your_key \
  uv run adventurelog-mcp --transport stdio
```

## Run with Docker

See [docker-compose.example.yml](docker-compose.example.yml). The MCP server must be able to reach AdventureLog
(`ADVENTURELOG_URL`). Put it behind HTTPS before exposing it to the internet: the API key travels in a header.

## Settings

| Variable | Default | |
| --- | --- | --- |
| `ADVENTURELOG_URL` | `http://app:80` | Where the AdventureLog API lives |
| `ADVENTURELOG_PUBLIC_URL` | same as above | Sent as `Origin`; set to your `SITE_URL` |
| `ADVENTURELOG_API_KEY` | | stdio only. Over HTTP it is ignored: each client sends its own key |
| `MCP_HOST`, `MCP_PORT` | `0.0.0.0`, `8017` | HTTP bind |
| `MCP_ALLOWED_HOSTS` | | Comma separated `Host` values to accept |
| `MCP_ALLOW_DESTRUCTIVE` | `false` | Enables the delete tools |

## Develop

```sh
uv sync
uv run pytest
uv run python scripts/live_smoke.py          # stage 1, against a real AdventureLog (.env), cleans up after itself
uv run python scripts/live_smoke_stage2.py   # stage 2 (day plan, world travel)
uv run python scripts/live_smoke_stage3.py   # stage 3 (edits, deletes, prompts)
uv run ruff check . && uv run ruff format --check .
```
