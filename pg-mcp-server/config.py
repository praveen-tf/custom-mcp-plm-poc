"""Application configuration, loaded from environment variables and `.env`.

All variables are namespaced with the ``PGMCP_`` prefix (e.g. ``PGMCP_DATABASE_URL``).
Missing required values raise a ``ValidationError`` at startup — fail fast.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Postgres MCP server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PGMCP_",
        case_sensitive=False,
        extra="ignore",
    )

    # Connection string for the least-privilege, read-only database role (required).
    database_url: str = Field(..., description="psycopg conninfo / URL for the read-only role")

    # Path to the access policy (table/column whitelist + query templates).
    policy_path: str = "policy.yaml"

    # HTTP server bind address (Streamable HTTP is served at /mcp/).
    host: str = "0.0.0.0"
    port: int = 8000

    # Query hardening.
    statement_timeout_ms: int = 5000
    max_rows: int = 200

    # OAuth 2.1 — required for the ChatGPT Enterprise connector, optional for local dev.
    # With Microsoft Entra ID as the authorization server, set issuer + jwks_uri + audience.
    oauth_issuer_url: str | None = None
    oauth_jwks_uri: str | None = None
    oauth_audience: str | None = None
    oauth_required_scopes: list[str] = ["pg.read"]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()  # type: ignore[call-arg]  # required fields are populated from env / .env
