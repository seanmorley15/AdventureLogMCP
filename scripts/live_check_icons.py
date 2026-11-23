"""A new category gets a fitting emoji, not the default globe."""

import asyncio
import sys

import httpx

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _live import live  # noqa: E402

from adventurelog_mcp.config import get_settings  # noqa: E402


async def main() -> int:
    async with live() as t:
        loc = await t.call(
            "create_location", name="Icon check", latitude=10.1, longitude=10.1, category="Brewery", show=0
        )
        t.cleanup.append(f"/api/locations/{loc['id']}/")
        cats = await t.call("list_categories", show=0)
        t.check("category exists", any(c["display_name"] == "Brewery" for c in cats["categories"]))
        async with httpx.AsyncClient(base_url=get_settings().adventurelog_url) as h:
            raw = (await h.get("/api/categories/", headers={"X-API-Key": t.key})).json()
        icon = next(c["icon"] for c in raw if c["display_name"] == "Brewery")
        print("   icon:", icon)
        t.check("fitting emoji, not the globe", icon == "🍺")
        t.cleanup.append(f"/api/categories/{next(c['id'] for c in raw if c['display_name'] == 'Brewery')}/")
    return 1 if t.errors else 0


sys.exit(asyncio.run(main()))
