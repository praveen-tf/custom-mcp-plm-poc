"""Tests for OAuth auth wiring (build_auth mode selection)."""

from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier

from auth import build_auth
from config import Settings

_TOKEN_VALIDATION = {
    "oauth_issuer_url": "https://login.microsoftonline.com/tenant/v2.0",
    "oauth_jwks_uri": "https://login.microsoftonline.com/tenant/discovery/v2.0/keys",
    "oauth_audience": "api://pg-mcp",
}
_AZURE_PROXY = {
    "oauth_client_id": "client-123",
    "oauth_client_secret": "secret-abc",
    "oauth_tenant_id": "tenant-xyz",
    "oauth_base_url": "https://pg-mcp-server.example.azurecontainerapps.io",
}


def _settings(**overrides) -> Settings:
    base = {"database_url": "postgresql://u:p@localhost/db"}
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_build_auth_returns_none_when_unconfigured():
    assert build_auth(_settings()) is None


def test_build_auth_returns_jwt_verifier_for_token_validation():
    auth = build_auth(_settings(**_TOKEN_VALIDATION))
    assert isinstance(auth, JWTVerifier)


def test_build_auth_returns_azure_proxy_when_proxy_vars_set():
    auth = build_auth(_settings(**_AZURE_PROXY))
    assert isinstance(auth, AzureProvider)


def test_azure_proxy_takes_precedence_over_token_validation():
    auth = build_auth(_settings(**_AZURE_PROXY, **_TOKEN_VALIDATION))
    assert isinstance(auth, AzureProvider)
