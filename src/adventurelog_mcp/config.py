"""Settings, read from the environment (see README for the full list)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Where the AdventureLog API lives. In docker compose this is the AIO `app` service.
    adventurelog_url: str = "http://app:80"
    # Sent as the `Origin` header. AdventureLog's web proxy refuses multipart and body-less writes
    # (DELETE) unless Origin equals the site's own address, so set this to your SITE_URL.
    adventurelog_public_url: str | None = None
    # Fallback key for stdio and single-user setups. HTTP clients send their own.
    adventurelog_api_key: str | None = None

    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8017
    # Comma separated Host values to accept (DNS-rebinding protection). Empty = no host check.
    mcp_allowed_hosts: str = ""
    # Registers the delete tools (stage 3).
    mcp_allow_destructive: bool = False

    request_timeout: float = Field(default=30.0, description="Seconds per AdventureLog request")

    @property
    def api_base(self) -> str:
        return self.adventurelog_url.rstrip("/")

    @property
    def origin(self) -> str:
        return (self.adventurelog_public_url or self.adventurelog_url).rstrip("/")

    @property
    def allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.mcp_allowed_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
