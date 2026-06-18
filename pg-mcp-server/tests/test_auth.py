"""Tests for OAuth auth wiring."""

from auth import build_auth
from config import Settings


def _settings(**overrides) -> Settings:
    base = {"database_url": "postgresql://u:p@localhost/db"}
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_build_auth_returns_none_when_unconfigured():
    assert build_auth(_settings()) is None


def test_build_auth_returns_verifier_when_configured():
    verifier = build_auth(
        _settings(
            oauth_issuer_url="https://login.microsoftonline.com/tenant/v2.0",
            oauth_jwks_uri="https://login.microsoftonline.com/tenant/discovery/v2.0/keys",
            oauth_audience="api://pg-mcp",
        )
    )
    assert verifier is not None
