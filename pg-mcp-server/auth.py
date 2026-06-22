"""OAuth 2.1 authentication for the MCP server.

The server supports three modes, selected by ``build_auth`` from settings:

1. **Azure OAuth proxy** (preferred; required for the ChatGPT connector). When the
   ``oauth_client_id`` / ``oauth_client_secret`` / ``oauth_tenant_id`` / ``oauth_base_url``
   settings are present, ``build_auth`` returns a FastMCP ``AzureProvider``. ChatGPT's
   connector discovers this server's OAuth metadata and dynamic-registration endpoints
   (DCR/CIMD + PKCE), and the provider proxies the login to a single Microsoft Entra app
   registration. This is needed because ChatGPT registers itself dynamically and Entra does
   not support open Dynamic Client Registration.

2. **Token-only validation** (resource server). When the ``oauth_issuer_url`` /
   ``oauth_jwks_uri`` / ``oauth_audience`` settings are present, ``build_auth`` returns a
   ``JWTVerifier`` that validates incoming bearer JWTs but exposes no discovery endpoints.

3. **No authentication** (local dev only). When neither mode is configured, ``build_auth``
   returns ``None``. Never expose an unauthenticated server publicly; the read-only database
   role and the whitelist still apply, but auth is the front door.
"""

from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier

from config import Settings
from logging_config import get_logger

logger = get_logger(__name__)


def build_auth(settings: Settings) -> AuthProvider | None:
    """Return the auth provider for the configured mode (see the module docstring)."""
    if (
        settings.oauth_client_id
        and settings.oauth_client_secret
        and settings.oauth_tenant_id
        and settings.oauth_base_url
    ):
        logger.info("OAuth enabled (Azure proxy, base_url=%s)", settings.oauth_base_url)
        return AzureProvider(
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret,
            tenant_id=settings.oauth_tenant_id,
            base_url=settings.oauth_base_url,
            required_scopes=settings.oauth_required_scopes,
            identifier_uri=settings.oauth_identifier_uri,
            jwt_signing_key=settings.oauth_jwt_signing_key,
        )

    if settings.oauth_issuer_url and settings.oauth_jwks_uri and settings.oauth_audience:
        logger.info("OAuth enabled (token validation, issuer=%s)", settings.oauth_issuer_url)
        return JWTVerifier(
            jwks_uri=settings.oauth_jwks_uri,
            issuer=settings.oauth_issuer_url,
            audience=settings.oauth_audience,
            required_scopes=settings.oauth_required_scopes,
        )

    logger.warning("OAuth not configured — running WITHOUT authentication (local dev only)")
    return None
