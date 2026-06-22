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

    # ── OAuth 2.1 ────────────────────────────────────────────────────────────
    # Two mutually exclusive modes, selected by build_auth() in this order. Leave
    # everything blank for local dev (no auth — never expose publicly).
    #
    # Mode 1 — Azure OAuth proxy (preferred; required for the ChatGPT connector).
    # FastMCP's AzureProvider publishes the OAuth discovery + dynamic-registration
    # endpoints ChatGPT needs and proxies login to ONE Entra app registration.
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_tenant_id: str | None = None
    # Public HTTPS base URL of THIS server, no trailing slash, e.g.
    # https://pg-mcp-server.<region>.azurecontainerapps.io — must match exactly.
    oauth_base_url: str | None = None
    # Optional: API identifier (defaults to api://<client_id>) and a stable JWT
    # signing key (set one for restart-stable / multi-replica sessions).
    oauth_identifier_uri: str | None = None
    oauth_jwt_signing_key: str | None = None

    # Mode 2 — token-only validation (resource server): validate incoming JWTs
    # against an external authorization server; no discovery/registration endpoints.
    oauth_issuer_url: str | None = None
    oauth_jwks_uri: str | None = None
    oauth_audience: str | None = None

    # Scopes required on the token (shared by both modes).
    oauth_required_scopes: list[str] = ["pg.read"]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()  # type: ignore[call-arg]  # required fields are populated from env / .env
