"""``adventurelog-mcp`` command line."""

from __future__ import annotations

import argparse

from .config import get_settings
from .server import build_http_app, build_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="adventurelog-mcp", description="AdventureLog MCP server")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    args = parser.parse_args()

    if args.transport == "stdio":
        build_server().run("stdio")
        return

    import uvicorn

    settings = get_settings()
    uvicorn.run(build_http_app(), host=settings.mcp_host, port=settings.mcp_port, log_level="info")


if __name__ == "__main__":
    main()
