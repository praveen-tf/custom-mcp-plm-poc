"""OAuth 2.1 bearer-token authentication for the MCP server.

ChatGPT (Enterprise) connects as an OAuth 2.1 client and sends a bearer JWT on every
request. This server is the OAuth Resource Server: it validates each token's signature
(against the authorization server's JWKS), issuer, audience, and required scopes. With
Microsoft Entra ID as the authorization server, point the settings at your tenant's
issuer and JWKS URI.

When OAuth is not configured, ``build_auth`` returns ``None`` (no authentication) — for
local development only. Never expose an unauthenticated server publicly; authorization is
also enforced by the read-only database role and the whitelist, but auth is the front door.
"""

from fastmcp.server.auth.providers.jwt import JWTVerifier

from config import Settings
from logging_config import get_logger

logger = get_logger(__name__)


def build_auth(settings: Settings) -> JWTVerifier | None:
    """Return a JWT verifier when OAuth is configured, otherwise ``None`` (dev only)."""
    if not (settings.oauth_issuer_url and settings.oauth_jwks_uri and settings.oauth_audience):
        logger.warning("OAuth not configured — running WITHOUT authentication (local dev only)")
        return None
    logger.info("OAuth enabled (issuer=%s)", settings.oauth_issuer_url)
    return JWTVerifier(
        jwks_uri=settings.oauth_jwks_uri,
        issuer=settings.oauth_issuer_url,
        audience=settings.oauth_audience,
        required_scopes=settings.oauth_required_scopes,
    )
