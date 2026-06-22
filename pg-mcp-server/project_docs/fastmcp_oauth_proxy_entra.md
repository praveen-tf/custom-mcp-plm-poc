# FastMCP OAuth Proxy & Entra ID Integration — Reference Summary

**Source:** [gofastmcp.com/servers/auth/oauth-proxy](https://gofastmcp.com/servers/auth/oauth-proxy), [gofastmcp.com/integrations/azure](https://gofastmcp.com/integrations/azure), [jlowin/fastmcp GitHub Repository](https://github.com/jlowin/fastmcp), [Microsoft Learn - Entra ID](https://learn.microsoft.com/en-us/entra/identity-platform/)

**Retrieved:** 2026-06-22

**Version:** FastMCP v3.4.2+

---

## Overview

**Problem Solved:** ChatGPT's MCP connector expects Dynamic Client Registration (DCR) support from OAuth providers. Microsoft Entra ID (Azure AD) does **not** support open/anonymous DCR—it requires pre-registered applications. FastMCP's **`OAuthProxy`** bridges this gap by presenting a DCR-compliant interface to MCP clients (like ChatGPT) while using a single fixed Entra app registration upstream.

**High-level flow:**
1. ChatGPT discovers MCP server's OAuth metadata at `/.well-known/oauth-protected-resource`
2. ChatGPT performs DCR (Dynamic Client Registration) with FastMCP's OAuthProxy
3. OAuthProxy validates the request, stores the DCR client, and returns a temporary `client_id`/`client_secret`
4. ChatGPT initiates OAuth authorization code + PKCE flow with OAuthProxy
5. OAuthProxy acts as a proxy: it forwards the request to Entra ID using its own pre-registered credentials (with its own PKCE)
6. After Entra ID redirects back, OAuthProxy exchanges the code, validates the upstream token, and issues its own FastMCP JWT to ChatGPT
7. ChatGPT (and all subsequent requests) uses the FastMCP JWT for authentication

---

## 1. OAuthProxy: Architecture & Endpoints

### Import & Constructor

```python
from fastmcp.server.auth.oauth_proxy.proxy import OAuthProxy

auth_provider = OAuthProxy(
    # Upstream (Entra ID) OAuth endpoints
    upstream_authorization_endpoint="https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize",
    upstream_token_endpoint="https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
    upstream_client_id="<your-entra-app-client-id>",
    upstream_client_secret="<your-entra-app-client-secret>",
    
    # Token verifier for validating upstream (Entra) tokens
    token_verifier=JWTVerifier(...),
    
    # Public base URL where OAuthProxy is accessible
    base_url="https://your-container-app.azurecontainerapps.io",
    
    # Callback path (default: "/auth/callback")
    redirect_path="/auth/callback",
    
    # Optional OIDC metadata publication
    issuer_url="https://your-container-app.azurecontainerapps.io",
    
    # PKCE forwarding (default: True)
    forward_pkce=True,
    
    # Enable Client Identity Metadata Document (CIMD) support (default: True)
    enable_cimd=True,
    
    # Allowed redirect URIs for DCR clients (e.g., ChatGPT)
    allowed_client_redirect_uris=["https://chatgpt.com/connector_platform_oauth_redirect"],
    
    # Scopes your server supports (advertised to clients)
    valid_scopes=["pg.read", "pg.write"],
)
```

### Exposed HTTP Endpoints

| Endpoint | Purpose | Details |
|----------|---------|---------|
| `/.well-known/oauth-protected-resource` | Protected Resource Metadata (PRM) discovery | ChatGPT queries this to discover the authorization server and supported scopes |
| `/.well-known/oauth-authorization-server` | OAuth Authorization Server metadata | Includes token endpoint, authorization endpoint, JWKS, supported grant types |
| `/register` (POST) | Dynamic Client Registration (RFC 7591) | ChatGPT POSTs client metadata here; OAuthProxy returns `client_id`, `client_secret` |
| `/authorize` (GET) | OAuth authorization initiation | Handles PKCE challenge, scopes, client validation; redirects to Entra ID |
| `/token` (POST) | Token exchange endpoint | Receives authorization code (+ PKCE verifier) from the client; exchanges for access token |
| `/auth/callback` | Redirect URI (configurable) | Entra ID redirects here after user authentication; OAuthProxy handles token exchange with Entra |
| `/.well-known/jwks.json` | JSON Web Key Set | OAuthProxy's public key for validating JWT tokens it issues to clients |

**Key insight:** OAuthProxy handles **TWO PKCE flows** simultaneously:
- **Client-to-OAuthProxy PKCE:** Validates the client's (ChatGPT's) PKCE challenge
- **OAuthProxy-to-Entra PKCE:** OAuthProxy generates its own PKCE pair and sends to Entra, protecting the proxy-to-provider channel

---

## 2. AzureProvider: Entra ID Specialization

FastMCP v3 provides a higher-level `AzureProvider` class that pre-configures OAuthProxy for Entra ID, handling Entra-specific token format and scope prefixing automatically.

### Import & Constructor

```python
from fastmcp.server.auth.providers.azure import AzureProvider

auth_provider = AzureProvider(
    client_id="835f09b6-0f0f-40cc-85cb-f32c5829a149",  # Your Entra app's Application (client) ID
    client_secret="<your-entra-app-secret>",
    tenant_id="08541b6e-646d-43de-a0eb-834e6713d6d5",  # Your Entra tenant ID
    
    # Public HTTPS URL where the server is reachable
    base_url="https://pg-mcp-server.azurecontainerapps.io",
    
    # Scopes your API exposes (unprefixed; FastMCP prefixes them with identifier_uri)
    required_scopes=["read", "write"],
    
    # Optional: custom Application ID URI (defaults to api://{client_id})
    identifier_uri="api://835f09b6-0f0f-40cc-85cb-f32c5829a149",
    
    # Optional: custom redirect path (defaults to "/auth/callback")
    redirect_path="/auth/callback",
    
    # Issuer URL for OAuth metadata (defaults to base_url)
    issuer_url="https://pg-mcp-server.azurecontainerapps.io",
    
    # Entra Graph scopes or other upstream scopes (not advertised to clients)
    additional_authorize_scopes=["User.Read"],
    
    # Allowed client redirect URIs for DCR
    allowed_client_redirect_uris=[
        "https://chatgpt.com/connector_platform_oauth_redirect",
    ],
    
    # JWT signing key for FastMCP tokens (optional; FastMCP generates one if not provided)
    jwt_signing_key=None,
    
    # Require user consent before authorizing a client (default: True)
    require_authorization_consent=True,
    
    # Azure Government or other authority (default: "login.microsoftonline.com")
    base_authority="login.microsoftonline.com",
    
    # Enable CIMD (Client Identity Metadata Document) support (default: True)
    enable_cimd=True,
)
```

**What AzureProvider does:**
- Constructs Entra v2.0 endpoints automatically (`/oauth2/v2.0/authorize`, `/oauth2/v2.0/token`)
- Sets the issuer to `https://login.microsoftonline.com/{tenant_id}/v2.0`
- Validates tokens with the Entra JWKS endpoint
- Handles Azure's scope format: unprefixed scopes (e.g., `"read"`) become `api://{client_id}/read`
- Enables CIMD (Client Identity Metadata Document) by default—modern ChatGPT uses CIMD instead of DCR when available

---

## 3. Token Verification: JWTVerifier & AzureJWTVerifier

For **OAuth proxy mode** (DCR + token exchange), use `JWTVerifier` configured for Entra:

```python
from fastmcp.server.auth.providers.jwt import JWTVerifier

token_verifier = JWTVerifier(
    jwks_uri="https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
    issuer="https://login.microsoftonline.com/{tenant_id}/v2.0",
    audience="api://835f09b6-0f0f-40cc-85cb-f32c5829a149",  # Your app's identifier_uri
    algorithm="RS256",
)
```

For **token-only verification mode** (when you only validate incoming tokens, no DCR), FastMCP provides `AzureJWTVerifier`:

```python
from fastmcp.server.auth.providers.azure import AzureJWTVerifier

token_verifier = AzureJWTVerifier(
    client_id="835f09b6-0f0f-40cc-85cb-f32c5829a149",
    tenant_id="08541b6e-646d-43de-a0eb-834e6713d6d5",
)
```

**Key differences:**
- `AzureJWTVerifier` pre-configures JWKS, issuer, and audience for you
- It handles Azure's scope format: tokens may have a `scp` claim with unprefixed scopes (e.g., `"read"`), while OAuth metadata advertises full URIs (e.g., `api://client_id/read`)
- Use `AzureJWTVerifier` if your server **only validates tokens** (typical for resource servers)
- Use `JWTVerifier` if you need more control or non-Azure providers

---

## 4. PKCE Handling in OAuthProxy

The proxy implements **dual PKCE** for end-to-end security:

### Step 1: Client-to-Proxy PKCE (ChatGPT ↔ OAuthProxy)
- ChatGPT generates `code_challenge` and sends it in `/authorize` request
- OAuthProxy stores the client's PKCE challenge
- Later, ChatGPT sends `code_verifier` during token exchange
- OAuthProxy validates the verifier against the stored challenge

### Step 2: Proxy-to-Upstream PKCE (OAuthProxy ↔ Entra ID)
- OAuthProxy generates its **own** PKCE pair (`code_verifier`, `code_challenge`)
- Sends the challenge to Entra ID's `/authorize` endpoint (if `forward_pkce=True`, default)
- After Entra redirects to OAuthProxy's `/auth/callback`, OAuthProxy uses its stored `code_verifier` to exchange with Entra

**Benefits:**
- Security at both layers: clients cannot see upstream provider credentials
- Upstream provider (Entra) never knows the client's PKCE; only the proxy's
- Tokens from Entra are immediately re-encrypted and wrapped in FastMCP JWTs

**To disable PKCE forwarding** (for legacy upstream providers that don't support it):
```python
auth_provider = OAuthProxy(..., forward_pkce=False)
```

---

## 5. Entra App Registration Requirements

### App A: Your MCP Server (Resource Server)

**Portal:** Entra Admin Center > App registrations > New registration

1. **Basic Info**
   - Name: `pg-mcp-server`
   - Supported account types: "Accounts in this organizational directory only" (single tenant)
   - No Redirect URI needed (this is the API, not a web app)

2. **Copy these values** (from the Overview page):
   - **Application (client) ID** — Use as `client_id` in AzureProvider
   - **Tenant ID** — Use as `tenant_id` in AzureProvider

3. **Expose an API** (Manage > Expose an API)
   - Click **Add** next to "Application ID URI"
   - Set: `api://<application-client-id>` (globally unique within your tenant)
   - Under **Scopes**, click **Add a scope**:
     - Scope name: `read` (FastMCP will advertise as `api://{client_id}/read`)
     - Who can consent: Admins and users
     - Admin consent display name: "Read-only access to Postgres via MCP"
     - Admin consent description: "Allow reading from the protected Postgres MCP server"
     - **Save**

4. **Certificates & secrets** (Manage > Certificates & secrets)
   - Click **New client secret**
   - Description: "pg-mcp-server client secret"
   - Expires: Recommend "24 months" (Azure default) or set a shorter rotation schedule
   - **Add**
   - **Copy the secret immediately** — you can only see it once; use as `client_secret` in AzureProvider

5. **Manifest** (Manage > Manifest)
   - Find line: `"requestedAccessTokenVersion": null` (or `1`)
   - Change to: `"requestedAccessTokenVersion": 2`
   - **Save**
   - **Why:** Forces Entra to issue v2.0 tokens with the correct `iss` claim (`https://login.microsoftonline.com/{tenant_id}/v2.0`)

### App B: OAuth Client (ChatGPT)

This is **not** a separate app registration. Instead, ChatGPT performs **Dynamic Client Registration (DCR)** or uses **CIMD** (Client Identity Metadata Document). The `allowed_client_redirect_uris` in AzureProvider defines which redirect URIs are accepted during DCR.

For testing or if you want to pre-register ChatGPT as a fixed client in Entra:
- **Required Permissions** (Manage > API permissions):
  - Add permission > My APIs > Select `pg-mcp-server` > Delegated permissions > Check `read`
  - **Grant admin consent**
- **Redirect URI** (Manage > Authentication > Web):
  - Add: `https://chatgpt.com/connector_platform_oauth_redirect`
- **Token configuration** (Manage > Token configuration):
  - Add optional claim: `scp` (scope) — this helps ChatGPT's token validation

---

## 6. Server Code Wiring (main.py & auth.py)

### Current (JWT Verifier Only)

```python
# auth.py
from fastmcp.server.auth.providers.jwt import JWTVerifier

def build_auth(settings: Settings) -> JWTVerifier | None:
    if not (settings.oauth_issuer_url and settings.oauth_jwks_uri and settings.oauth_audience):
        return None
    return JWTVerifier(
        jwks_uri=settings.oauth_jwks_uri,
        issuer=settings.oauth_issuer_url,
        audience=settings.oauth_audience,
        required_scopes=settings.oauth_required_scopes,
    )

# main.py
from auth import build_auth
mcp = FastMCP("pg-mcp-server", auth=build_auth(settings))
```

**Issue:** This setup only validates incoming JWTs; it does **not** expose OAuth metadata or handle DCR. ChatGPT cannot register clients.

### Upgraded (AzureProvider + OAuth Proxy)

```python
# auth.py
from fastmcp.server.auth.providers.azure import AzureProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier

def build_auth(settings: Settings) -> AzureProvider | JWTVerifier | None:
    """Return an auth provider: AzureProvider (DCR + OAuth), JWTVerifier (token-only), or None (dev)."""
    
    if not settings.oauth_client_id:
        # No OAuth configured; run without auth (dev only)
        return None
    
    if settings.oauth_proxy_enabled:
        # Use AzureProvider: DCR + OAuth proxy for ChatGPT
        if not (settings.oauth_client_secret and settings.oauth_tenant_id and settings.oauth_base_url):
            raise ValueError(
                "AzureProvider requires: oauth_client_id, oauth_client_secret, "
                "oauth_tenant_id, oauth_base_url"
            )
        
        return AzureProvider(
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret,
            tenant_id=settings.oauth_tenant_id,
            base_url=settings.oauth_base_url,
            required_scopes=settings.oauth_required_scopes,
            identifier_uri=settings.oauth_identifier_uri,
            redirect_path="/auth/callback",
            additional_authorize_scopes=settings.oauth_additional_scopes,
            allowed_client_redirect_uris=settings.oauth_allowed_client_redirect_uris,
            enable_cimd=True,
        )
    else:
        # Use JWTVerifier: token-only validation (for RemoteAuthProvider or Managed Identity)
        if not (settings.oauth_issuer_url and settings.oauth_jwks_uri and settings.oauth_audience):
            raise ValueError(
                "JWTVerifier requires: oauth_issuer_url, oauth_jwks_uri, oauth_audience"
            )
        
        return JWTVerifier(
            jwks_uri=settings.oauth_jwks_uri,
            issuer=settings.oauth_issuer_url,
            audience=settings.oauth_audience,
            algorithm="RS256",
        )

# config.py (add these fields)
class Settings(BaseSettings):
    # OAuth mode: "azure_proxy" (DCR + OAuth), "jwt_verify" (token-only), or None (no auth)
    oauth_proxy_enabled: bool = False
    
    # OAuth Proxy (AzureProvider) settings
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_tenant_id: str | None = None
    oauth_base_url: str | None = None  # e.g., https://pg-mcp-server.azurecontainerapps.io
    oauth_identifier_uri: str | None = None  # Defaults to api://{oauth_client_id}
    oauth_allowed_client_redirect_uris: list[str] = ["https://chatgpt.com/connector_platform_oauth_redirect"]
    oauth_additional_scopes: list[str] = []
    
    # OAuth Token Validation (JWTVerifier) settings
    oauth_issuer_url: str | None = None
    oauth_jwks_uri: str | None = None
    oauth_audience: str | None = None
    oauth_required_scopes: list[str] = ["api://835f09b6-0f0f-40cc-85cb-f32c5829a149/read"]

# main.py
mcp = FastMCP("pg-mcp-server", auth=build_auth(settings))
```

**Environment variables** (.env):
```bash
# For AzureProvider (OAuth Proxy)
PGMCP_OAUTH_PROXY_ENABLED=true
PGMCP_OAUTH_CLIENT_ID=835f09b6-0f0f-40cc-85cb-f32c5829a149
PGMCP_OAUTH_CLIENT_SECRET=<your-app-secret>
PGMCP_OAUTH_TENANT_ID=08541b6e-646d-43de-a0eb-834e6713d6d5
PGMCP_OAUTH_BASE_URL=https://pg-mcp-server.azurecontainerapps.io
PGMCP_OAUTH_IDENTIFIER_URI=api://835f09b6-0f0f-40cc-85cb-f32c5829a149
PGMCP_OAUTH_REQUIRED_SCOPES=read,write

# For JWTVerifier (token-only)
PGMCP_OAUTH_ISSUER_URL=https://login.microsoftonline.com/08541b6e-646d-43de-a0eb-834e6713d6d5/v2.0
PGMCP_OAUTH_JWKS_URI=https://login.microsoftonline.com/08541b6e-646d-43de-a0eb-834e6713d6d5/discovery/v2.0/keys
PGMCP_OAUTH_AUDIENCE=api://835f09b6-0f0f-40cc-85cb-f32c5829a149
```

---

## 7. ChatGPT Connector OAuth Flow (from ChatGPT's perspective)

### Discovery Phase
1. ChatGPT queries: `GET https://your-server/mcp/.well-known/oauth-protected-resource`
2. Response includes:
   ```json
   {
     "resource": "api://835f09b6-0f0f-40cc-85cb-f32c5829a149",
     "authorization_servers": [
       "https://your-server.azurecontainerapps.io"
     ],
     "scopes_supported": ["api://835f09b6-0f0f-40cc-85cb-f32c5829a149/read"]
   }
   ```
3. ChatGPT then queries: `GET https://your-server/.well-known/oauth-authorization-server`
4. Response includes token endpoint, authorization endpoint, JWKS, etc.

### DCR (or CIMD) Phase
- **CIMD (preferred by modern ChatGPT):** ChatGPT sends a CIMD URL as the `client_id` parameter; OAuthProxy validates the URL and extracts client metadata from it
- **DCR (legacy, still supported):** ChatGPT POSTs to `/register` with `redirect_uris`, `client_name`, etc.; OAuthProxy stores the registration and returns `client_id`/`client_secret`

### Authorization Phase
1. ChatGPT initiates: `GET /authorize?client_id=...&redirect_uri=https://chatgpt.com/...&code_challenge=...&code_challenge_method=S256&scope=api://...&state=...`
2. OAuthProxy stores the PKCE challenge and redirects to Entra:
   ```
   GET https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize
       ?client_id=835f09b6-0f0f-40cc-85cb-f32c5829a149
       &redirect_uri=https://your-server/auth/callback
       &code_challenge=<proxy-generated-challenge>
       &code_challenge_method=S256
       &scope=api://835f09b6.../read%20offline_access
       &...
   ```
3. User logs in to Entra; Entra redirects to OAuthProxy's callback:
   ```
   GET https://your-server/auth/callback?code=<auth_code>&state=<state>
   ```
4. OAuthProxy exchanges the code with Entra using its own `code_verifier`, gets an access token
5. OAuthProxy then redirects ChatGPT's browser back to its original `redirect_uri`:
   ```
   GET https://chatgpt.com/connector_platform_oauth_redirect?code=<client-code>&state=<state>
   ```

### Token Exchange Phase
1. ChatGPT POSTs to `/token`:
   ```
   POST /token
   grant_type=authorization_code
   code=<client-code>
   code_verifier=<client-verifier>
   client_id=<client_id>
   client_secret=<client_secret>  (if DCR was used; CIMD public clients omit this)
   ```
2. OAuthProxy validates the PKCE verifier, exchanges the code, and returns:
   ```json
   {
     "access_token": "eyJhbGciOiJIUzI1NiIs...",  // FastMCP JWT
     "token_type": "Bearer",
     "expires_in": 3600
   }
   ```
3. ChatGPT uses this JWT on every tool call: `Authorization: Bearer <access_token>`

---

## 8. Base URL & Public HTTPS Requirements

### Critical Gotchas

| Gotcha | Impact | Solution |
|--------|--------|----------|
| **base_url must match public hostname exactly** | OAuth metadata, redirect URIs, and token validation all use this URL | Set `PGMCP_OAUTH_BASE_URL` to the **exact** public HTTPS FQDN (e.g., `https://pg-mcp-server.azurecontainerapps.io`, no trailing slash) |
| **Trailing slashes cause 301 redirects** | Some clients strip Authorization headers during redirects, causing 401/400 errors | Do **not** include trailing slash: `https://host/mcp` ✓ vs. `https://host/mcp/` ✗ |
| **Must be HTTPS, publicly accessible** | OAuth requires secure transport; Entra won't redirect to HTTP | Deploy on Azure Container Apps (auto HTTPS); use ngrok/Cloudflare Tunnel for local testing |
| **Callback path must match Entra registration** | If you customize `redirect_path`, update the Redirect URI in the Entra app registration | Default is `/auth/callback`; if you change it to `/oauth/callback`, register that URI in Entra |
| **Issuer URL mismatch in token validation** | Entra v2.0 tokens have `iss = https://login.microsoftonline.com/{tenant_id}/v2.0` (note `/v2.0` suffix) | Use exact Entra v2.0 issuer in `JWTVerifier`; AzureProvider handles this automatically |
| **base_url path component stripped during DCR** | Some OAuth proxy implementations strip URL paths, breaking servers at paths like `/api/v1/mcp` | FastMCP preserves paths correctly; ensure `base_url` is the root, or use a reverse-proxy path rewrite |

---

## 9. Known Gotchas & Fixes

### Token Audience Mismatch
**Symptom:** 401 "invalid audience" errors
- **Root cause:** Token `aud` claim doesn't match the `audience` parameter in JWTVerifier
- **Typical mistake:** Using `client_id` (e.g., `835f09b...`) instead of `identifier_uri` (e.g., `api://835f09b...`)
- **Fix:** Set `audience` to the full **Application ID URI** you configured in Entra ("Expose an API")

```python
# Wrong
token_verifier = JWTVerifier(audience="835f09b6-0f0f-40cc-85cb-f32c5829a149")

# Correct
token_verifier = JWTVerifier(audience="api://835f09b6-0f0f-40cc-85cb-f32c5829a149")
```

### Issuer Mismatch (v1.0 vs v2.0)
**Symptom:** 401 "invalid issuer" errors
- **Root cause:** Entra is issuing v1.0 tokens (`iss = https://sts.windows.net/...`) but verifier expects v2.0
- **Root cause:** `requestedAccessTokenVersion` in Entra app manifest is not set to `2`
- **Fix:** In Entra Admin Center, open the app registration > Manage > Manifest, set `"requestedAccessTokenVersion": 2`, then Save

### Clock Skew
**Symptom:** Tokens rejected as expired even though they should be valid
- **Root cause:** Server clock is out of sync with Entra's clock
- **Fix:** Ensure the Container Apps instance has NTP configured; Azure Container Apps syncs automatically, but verify in CI/CD logs

### Base URL Not Reachable from ChatGPT
**Symptom:** ChatGPT cannot reach the server during OAuth callback
- **Root cause:** `base_url` is a private IP, not publicly routable
- **Fix:** Deploy to Azure Container Apps (auto public HTTPS); for local testing, use ngrok or Cloudflare Tunnel

### ChatGPT Connector Cannot Be Updated Post-Publish
**Symptom:** After publishing a connector, OpenAI does not allow editing the OAuth settings
- **Behavior:** ChatGPT Business requires deleting and recreating the connector to change auth settings
- **Workaround:** Test OAuth settings thoroughly before publishing; if you must change auth, create a new connector and migrate users

---

## 10. What This Means for pg-mcp-server Deployment

### Option A: Full OAuth Proxy (Recommended for ChatGPT)
- **Use:** `AzureProvider` in FastMCP
- **Entra setup:** One app registration (the API server)
- **ChatGPT sees:** Full OAuth 2.1 + DCR/CIMD support
- **Deployment:** Azure Container Apps with public HTTPS URL
- **Code change:** Minimal—replace `JWTVerifier` with `AzureProvider` in `auth.py`
- **Environment:** Set `PGMCP_OAUTH_PROXY_ENABLED=true` + proxy-specific env vars

**auth.py diff:**
```python
# OLD
def build_auth(settings: Settings) -> JWTVerifier | None:
    if not (settings.oauth_issuer_url and settings.oauth_jwks_uri and settings.oauth_audience):
        return None
    return JWTVerifier(...)

# NEW
def build_auth(settings: Settings) -> AzureProvider | JWTVerifier | None:
    if not settings.oauth_client_id:
        return None
    
    if settings.oauth_proxy_enabled:
        return AzureProvider(
            client_id=settings.oauth_client_id,
            client_secret=settings.oauth_client_secret,
            tenant_id=settings.oauth_tenant_id,
            base_url=settings.oauth_base_url,
            required_scopes=settings.oauth_required_scopes,
        )
    else:
        return JWTVerifier(...)
```

### Option B: Token-Only Verification (for pre-registered clients)
- **Use:** `JWTVerifier` (existing setup)
- **Limitation:** ChatGPT cannot dynamically register; requires pre-registered client with fixed secret
- **ChatGPT connector:** User must manually paste `client_id`/`client_secret` (OpenAI does **not** accept this flow officially; DCR/CIMD required)
- **Deployment:** Same as Option A
- **Code change:** None—keep current `auth.py`

### Option C: Azure Managed Identity (for production auth only)
- **Use:** `AzureJWTVerifier` + `RemoteAuthProvider`
- **Benefit:** No client secrets in environment; uses Container Apps' Managed Identity
- **Limitation:** Token-only verification; no OAuth proxy (unsuitable for ChatGPT)
- **Documentation:** See Microsoft Learn article on Managed Identity + MCP
- **Deployment:** Azure Container Apps with Managed Identity + RBAC

**Recommendation:** Start with **Option A** (AzureProvider) for ChatGPT integration. It's the modern, supported path. Option B is a fallback if you only need token validation from pre-authorized clients.

---

## 11. Testing the OAuth Flow Locally

### Prerequisites
- FastMCP v3.4.2+ installed
- Entra app registration with client secret
- Public HTTPS URL (ngrok / Cloudflare Tunnel)

### Steps
1. Create `.env`:
   ```bash
   PGMCP_OAUTH_PROXY_ENABLED=true
   PGMCP_OAUTH_CLIENT_ID=<your-app-client-id>
   PGMCP_OAUTH_CLIENT_SECRET=<your-app-secret>
   PGMCP_OAUTH_TENANT_ID=<your-tenant-id>
   PGMCP_OAUTH_BASE_URL=https://your-ngrok-url.ngrok.io
   PGMCP_OAUTH_IDENTIFIER_URI=api://<your-app-client-id>
   ```

2. Start ngrok:
   ```bash
   ngrok http 8000
   ```
   Copy the `https://...ngrok.io` URL into `PGMCP_OAUTH_BASE_URL`.

3. Run server:
   ```bash
   uv run uvicorn main:app --host 0.0.0.0 --port 8000
   ```

4. Test discovery:
   ```bash
   curl https://your-ngrok-url.ngrok.io/.well-known/oauth-protected-resource
   ```
   You should see OAuth metadata.

5. Test DCR (optional):
   ```bash
   curl -X POST https://your-ngrok-url.ngrok.io/register \
     -H "Content-Type: application/json" \
     -d '{
       "client_name": "Test Client",
       "redirect_uris": ["https://example.com/callback"]
     }'
   ```
   Response should include `client_id` and `client_secret`.

---

## 12. References

- [FastMCP OAuth Proxy Documentation](https://gofastmcp.com/servers/auth/oauth-proxy)
- [FastMCP Azure (Entra) Integration](https://gofastmcp.com/integrations/azure)
- [FastMCP GitHub - OAuthProxy source](https://github.com/jlowin/fastmcp)
- [Microsoft Learn - Entra Platform](https://learn.microsoft.com/en-us/entra/identity-platform/)
- [RFC 7591 - Dynamic Client Registration](https://tools.ietf.org/html/rfc7591)
- [OAuth 2.0 PKCE (RFC 7636)](https://tools.ietf.org/html/rfc7636)
- [MCP Protected Resource Metadata](https://spec.modelcontextprotocol.io/latest/spec/server/#protected-resources)
- [OpenAI Apps SDK - Authentication](https://developers.openai.com/apps-sdk/build/auth)
