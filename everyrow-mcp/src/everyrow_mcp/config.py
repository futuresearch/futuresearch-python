from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PositiveInt, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    transport: str = Field(default="stdio")

    everyrow_api_url: str = Field(default="https://everyrow.io/api/v0")
    preview_size: int = Field(default=1000)
    max_inline_rows: int = Field(
        default=50_000,
        description="Maximum number of rows allowed in inline JSON data",
    )
    max_inline_data_bytes: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum size in bytes for inline CSV string data (10 MB)",
    )
    max_schema_properties: int = Field(
        default=50,
        description="Maximum number of properties allowed in a response schema",
    )
    token_budget: int = Field(
        default=20000,
        description="Target token budget per page of inline results",
    )

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=13)
    redis_password: str | None = Field(default=None)
    redis_sentinel_endpoints: str | None = Field(
        default=None, description="Comma-separated host:port pairs"
    )
    redis_sentinel_master_name: str | None = Field(default=None)

    trust_proxy_headers: bool = Field(
        default=False,
        description="Trust X-Forwarded-For and CF-Connecting-IP headers for client IP. "
        "Enable only when behind a trusted reverse proxy (e.g. Cloudflare).",
    )

    # HTTP-only settings — unused in stdio mode
    mcp_server_url: str = Field(default="")
    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="")

    registration_rate_limit: PositiveInt = Field(
        default=10,
        description="Max registrations/authorizations per IP per rate window",
    )
    registration_rate_window: PositiveInt = Field(
        default=60,
        description="Rate limit sliding window in seconds",
    )

    access_token_ttl: PositiveInt = Field(
        default=3300,
        description="Access token TTL in seconds (55 min, before Supabase JWT 1h expiry)",
    )
    auth_code_ttl: PositiveInt = Field(
        default=300,
        description="Authorization code TTL in seconds",
    )
    pending_auth_ttl: PositiveInt = Field(
        default=600,
        description="Pending authorization TTL in seconds",
    )
    client_registration_ttl: PositiveInt = Field(
        default=2_592_000,
        description="Client registration TTL in seconds (30 days)",
    )
    refresh_token_ttl: PositiveInt = Field(
        default=604_800,
        description="Refresh token TTL in seconds (7 days)",
    )
    everyrow_api_key: str | None = None

    @property
    def is_http(self) -> bool:
        return self.transport == "streamable-http"

    @property
    def is_stdio(self) -> bool:
        return self.transport == "stdio"

    @field_validator("mcp_server_url", "supabase_url")
    @classmethod
    def _strip_url_slashes(cls, v: str) -> str:
        return v.rstrip("/")


@lru_cache
def _get_settings():
    settings_instance = Settings()  # pyright: ignore[reportCallIssue]
    return settings_instance


settings = _get_settings()
