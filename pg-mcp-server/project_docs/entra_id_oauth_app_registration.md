# Microsoft Entra ID OAuth 2.0/2.1 App Registration — Reference Summary

**Source:** [Microsoft Learn - Entra ID Platform](https://learn.microsoft.com/en-us/entra/identity-platform/)
**Retrieved:** 2026-06-18
**Version:** v2.0 token version (requestedAccessTokenVersion = 2)

## Overview

This doc covers the **two-app-registration pattern** for OAuth 2.0/2.1: **App A** (the protected API/resource server) and **App B** (the client, e.g. ChatGPT Enterprise). For pg-mcp-server, this is a **read-only HTTPS OAuth resource server** that validates JWT bearer tokens against Entra ID's JWKS endpoint. Entra ID *issues* the tokens; the server *validates* them. The critical difference between v1.0 and v2.0 tokens is the issuer (`iss`) claim and how the access token is formatted—v2.0 is required for this setup to work.

---

## App A: OAuth Resource Server (pg-mcp-server)

### Register the API Application

**Portal path:** Entra admin center > App registrations > New registration

1. **Basic info:**
   - Name: `pg-mcp-server` (or similar)
   - Supported account types: "Accounts in this organizational directory only" (single tenant)
   - No Redirect URI needed (this is a backend API, not a web app)

2. **Copy these values** from the Overview page:
   - Application (client) ID — use this as the Resource Server identifier in App B's API permissions
   - Tenant ID — use in `PGMCP_OAUTH_ISSUER_URL` and `PGMCP_OAUTH_JWKS_URI`

### Expose an API

**Portal path:** App A registration > Manage > Expose an API

1. **Add Application ID URI** (if not auto-set):
   - Click **Add** next to "Application ID URI"
   - Set value: `api://<appA-client-id>` (where appA-client-id is your App A's Application (client) ID from step above)
   - This URI must be globally unique within your tenant and acts as the prefix for scopes
   - **Save**

2. **Add a scope:**
   - Click **Add a scope**
   - **Scope name:** `pg.read` (or `pg:read`)
   - **Who can consent:** Choose based on your org; recommend "Admins and users" for read-only ops, or "Admins only" if more restricted
   - **Admin consent display name:** "Read-only access to Postgres via MCP"
   - **Admin consent description:** "Allow the application to read data from the protected Postgres MCP server via OAuth 2.0 tokens."
   - **User consent display name:** (optional) "Access Postgres data"
   - **User consent description:** (optional) "Your app will have read-only access to Postgres data through the MCP server."
   - **State:** Enabled
   - **Add scope**

   Result: Full scope string = `api://<appA-client-id>/pg.read`

### Set Manifest: requestedAccessTokenVersion = 2

**Portal path:** App A registration > Manage > Manifest

**Why this is critical:** Setting `requestedAccessTokenVersion = 2` forces Entra ID to issue v2.0 access tokens, which have:
- `iss` claim = `https://login.microsoftonline.com/<tenant-id>/v2.0` (NOT `https://sts.windows.net/<tenant-id>/`)
- Token format aligned with the v2.0 endpoint `/oauth2/v2.0/token`
- Proper `aud` claim matching `api://<appA-client-id>`

Without this, you'll get v1.0 tokens with `iss = https://sts.windows.net/<tenant>/` and the server will reject them with 401 (invalid issuer).

1. Open **Manifest**
2. Find the line `"requestedAccessTokenVersion": null` (or `1`)
3. Change to: `"requestedAccessTokenVersion": 2`
4. **Save**

Example (abbreviated):
```json
{
  "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "name": "pg-mcp-server",
  "appId": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
  "requiredResourceAccess": [],
  "requestedAccessTokenVersion": 2,
  "identifierUris": ["api://yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"],
  "oauth2Permissions": [
    {
      "adminConsentDescription": "Allow the app to access resources on behalf of the signed-in user.",
      "adminConsentDisplayName": "Read-only access to Postgres via MCP",
      "id": "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz",
      "isEnabled": true,
      "type": "User",
      "userConsentDescription": "Your app will have read-only access to Postgres data through the MCP server.",
      "userConsentDisplayName": "Access Postgres data",
      "value": "pg.read"
    }
  ]
}
```

### Environment Variables for pg-mcp-server

After configuring App A, set these env vars on the server:

```bash
PGMCP_OAUTH_ISSUER_URL=https://login.microsoftonline.com/<TENANT_ID>/v2.0
PGMCP_OAUTH_JWKS_URI=https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys
PGMCP_OAUTH_AUDIENCE=api://<appA-client-id>
PGMCP_OAUTH_REQUIRED_SCOPE=pg.read
```

Replace:
- `<TENANT_ID>` with your Microsoft Entra tenant ID (a GUID, e.g., `aaaabbbb-0000-cccc-1111-dddd2222eeee`)
- `<appA-client-id>` with App A's Application (client) ID

The server uses these to fetch the JWKS public keys and validate incoming JWT bearer tokens.

---

## App B: OAuth Client (e.g., ChatGPT Enterprise)

### Register the Client Application

**Portal path:** Entra admin center > App registrations > New registration

1. **Basic info:**
   - Name: `chatgpt-pg-connector` (or similar)
   - Supported account types: "Accounts in this organizational directory only"
   - Redirect URI: (leave blank for now; ChatGPT will provide the callback URL later)

2. **Copy these values** from the Overview page:
   - Application (client) ID — share with the connector setup
   - Tenant ID — for the authorize/token endpoint

### Create a Client Secret

**Portal path:** App B registration > Manage > Certificates & secrets

1. Click **New client secret**
2. **Description:** "ChatGPT MCP Connector"
3. **Expires:** Choose based on your security policy (e.g., "12 months" for simplicity, or shorter for tighter control)
4. **Add**
5. **Copy the secret value immediately** (it is not shown again). Store in a secure vault or environment variable.

### Add API Permissions (Delegated)

**Portal path:** App B registration > Manage > API permissions

1. Click **Add a permission**
2. **Select an API:** Click **My APIs** tab
3. **Find and select App A** (the one you named `pg-mcp-server`)
4. **Request API permissions:**
   - Select **Delegated permissions**
   - Check the box for `pg.read` (or `pg:read`)
   - **Add permissions**

5. **Grant admin consent:**
   - The permission now appears in the list as "pg.read (Delegated)"
   - Click **Grant admin consent for [tenant]**
   - Confirm

This allows App B to request tokens for App A's `pg.read` scope on behalf of the signed-in user.

### Add Redirect URI (from ChatGPT)

**Portal path:** App B registration > Manage > Authentication

Once ChatGPT Enterprise connector is set up, it will provide a **redirect URI** (callback URL). Add it:

1. Click **Add a platform** or **Web**
2. **Redirect URIs:** Paste the ChatGPT redirect URI (e.g., `https://chatgpt.openai.com/aip/plugin/...`)
3. Under **Implicit grant and hybrid flows** (usually not needed for auth code flow, but may be auto-enabled):
   - Ensure **Access tokens** and **ID tokens** are unchecked (not needed for this OAuth client)
4. **Save**

**Alternative:** If using a custom connector, you may also configure:
- **Front-channel logout URL** (if needed for sign-out)

---

## OAuth 2.0 Endpoints & Token Flow

### Authorize Endpoint

Initiate user login and consent:

```
https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize
```

**Typical query parameters (ChatGPT or client initiates):**

```
GET /oauth2/v2.0/authorize?
  client_id=<appB-client-id>
  &response_type=code
  &redirect_uri=<URL-encoded-redirect-URI>
  &scope=api%3A%2F%2F<appA-client-id>%2Fpg.read+offline_access+openid
  &state=<random-string>
  &code_challenge=<PKCE-challenge>
  &code_challenge_method=S256
```

**Key points:**
- `scope`: Space-separated list: `api://<appA-client-id>/pg.read offline_access openid`
  - `api://<appA-client-id>/pg.read` — permission to read Postgres
  - `offline_access` — request refresh token (optional but recommended)
  - `openid` — request ID token (optional)
- `code_challenge` & `code_challenge_method=S256` — PKCE (recommended for all clients, required for SPAs)
- User signs in and consents to `pg.read` on behalf of App B

**Response (on success):**
```
GET <redirect-uri>?code=<authorization-code>&state=<state>
```

### Token Endpoint

Exchange authorization code for access token:

```
POST https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

client_id=<appB-client-id>
&client_secret=<appB-secret>
&code=<authorization-code>
&redirect_uri=<redirect-URI>
&grant_type=authorization_code
&code_verifier=<PKCE-verifier>
&scope=api%3A%2F%2F<appA-client-id>%2Fpg.read
```

**Response (on success):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IjEyMzQ1Njc4OWFiY2RlZiIsImtpZCI6IjEyMzQ1Njc4OWFiY2RlZiJ9...",
  "token_type": "Bearer",
  "expires_in": 3599,
  "scope": "api://yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy/pg.read",
  "refresh_token": "0.AXAAQoJk5L...",
  "id_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0..."
}
```

---

## Token Validation on pg-mcp-server

When the client (ChatGPT) calls pg-mcp-server with a bearer token:

```http
GET /api/postgres/query
Authorization: Bearer <access_token>
```

pg-mcp-server must validate:

1. **Token signature:** Verify using the public key from `PGMCP_OAUTH_JWKS_URI` (the JWKS endpoint)
2. **Issuer (`iss`):** Must equal `https://login.microsoftonline.com/<TENANT_ID>/v2.0`
3. **Audience (`aud`):** Must equal `api://<appA-client-id>` (set in `PGMCP_OAUTH_AUDIENCE`)
4. **Scope (`scp`):** Must include `pg.read`
5. **Expiration (`exp`):** Token must not be expired
6. **Token version:** Should be v2 (indicated by the `iss` claim containing `/v2.0` and matching manifest setting)

### Token Claims Reference

**v2.0 access token (correct setup):**

```json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "<key-id>"
}
{
  "iss": "https://login.microsoftonline.com/<TENANT_ID>/v2.0",
  "aud": "api://<appA-client-id>",
  "scp": "pg.read",
  "sub": "<user-subject>",
  "tid": "<TENANT_ID>",
  "exp": 1719781234,
  "iat": 1719777634,
  "ver": "2.0"
}
```

**v1.0 access token (WRONG — do not accept):**

```json
{
  "iss": "https://sts.windows.net/<TENANT_ID>/",
  "aud": "<appA-client-id>",
  "scp": "pg.read",
  ...
}
```

If you see `iss = https://sts.windows.net/`, it means `requestedAccessTokenVersion` was not set to 2 in App A's manifest. Fix the manifest and re-issue the token.

---

## Debugging with jwt.ms

To inspect and validate tokens during development:

1. Copy the full bearer token (without "Bearer " prefix) from a token response or API request
2. Go to **https://jwt.ms**
3. Paste the token
4. Verify:
   - **Header → alg:** `RS256`
   - **Payload → iss:** `https://login.microsoftonline.com/<TENANT_ID>/v2.0` (must have `/v2.0`)
   - **Payload → aud:** `api://<appA-client-id>` (must match your App A's Application ID URI)
   - **Payload → scp:** Contains `pg.read`
   - **Payload → exp:** Epoch time in the future
   - **Payload → ver:** `2.0`

If `iss` shows `https://sts.windows.net/...`, the token is v1.0 and will be rejected. Cause: `requestedAccessTokenVersion` is not set to 2 in App A's manifest.

---

## Azure Portal Menu Map

Quick reference for where each configuration lives:

| Config | Portal Path |
|--------|-----------|
| **App A: Basic Info** | Entra admin center > App registrations > select App A > Overview |
| **App A: Expose API** | App A > Manage > Expose an API |
| **App A: Scopes** | App A > Manage > Expose an API > Add a scope |
| **App A: Manifest** | App A > Manage > Manifest (edit `requestedAccessTokenVersion = 2`) |
| **App B: Basic Info** | Entra admin center > App registrations > select App B > Overview |
| **App B: Client Secret** | App B > Manage > Certificates & secrets > New client secret |
| **App B: API Permissions** | App B > Manage > API permissions > Add a permission |
| **App B: Redirect URI** | App B > Manage > Authentication > Add a platform (Web) |
| **App B: Grant Admin Consent** | App B > Manage > API permissions > Grant admin consent for [tenant] |

---

## Common Gotchas & Debugging

### 401 Invalid Issuer

**Symptom:** Server rejects tokens with HTTP 401 "invalid issuer"

**Cause:** Token has `iss = https://sts.windows.net/<tenant>/` instead of `https://login.microsoftonline.com/<tenant>/v2.0`

**Fix:**
1. Go to App A registration > Manage > Manifest
2. Verify `"requestedAccessTokenVersion": 2` is set (not `null` or `1`)
3. Save and wait ~5 minutes for changes to propagate
4. Request a new token (old tokens remain v1.0)

### 401 Invalid Audience

**Symptom:** Server rejects with "invalid audience"

**Cause:** Token `aud` claim does not match `PGMCP_OAUTH_AUDIENCE`

**Fix:**
1. Check token `aud` at jwt.ms
2. Verify `PGMCP_OAUTH_AUDIENCE` env var is set to `api://<appA-client-id>` (exact match)
3. Verify App A's Manifest has `"identifierUris": ["api://<appA-client-id>"]` with the same value

### 401 Invalid Scope

**Symptom:** Server rejects with "required scope not present"

**Cause:** Token `scp` claim does not include `pg.read`

**Fix:**
1. In the authorize request, include scope `api://<appA-client-id>/pg.read` (full scope string)
2. Verify App B has API permission granted for App A's `pg.read` scope
3. Verify App B has admin consent granted
4. Check token at jwt.ms for `"scp": "pg.read"`

### No Refresh Token in Response

**Symptom:** Token response lacks `refresh_token`

**Cause:** Forgot to include `offline_access` scope in the authorize request

**Fix:** In authorize endpoint, add scope `offline_access`:
```
scope=api://...../pg.read+offline_access+openid
```

---

## Environment Variables Summary (pg-mcp-server)

```bash
# OAuth Issuer & Keys Endpoint (v2.0 format)
PGMCP_OAUTH_ISSUER_URL=https://login.microsoftonline.com/<TENANT_ID>/v2.0
PGMCP_OAUTH_JWKS_URI=https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys

# Audience (must match App A's Application ID URI)
PGMCP_OAUTH_AUDIENCE=api://<appA-client-id>

# Required Scope for Authorization
PGMCP_OAUTH_REQUIRED_SCOPE=pg.read
```

Replace `<TENANT_ID>` and `<appA-client-id>` with your actual values from Entra admin center.

---

## References

- [Scopes and Permissions in the Microsoft Identity Platform](https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc)
- [How to Configure an Application to Expose a Web API](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-configure-app-expose-web-apis)
- [Microsoft Entra App Manifest Reference](https://learn.microsoft.com/en-us/entra/identity-platform/reference-app-manifest)
- [Access Tokens in the Microsoft Identity Platform](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens)
- [OAuth 2.0 Authorization Code Flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Expose Scopes in a Protected Web API](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-protected-web-api-expose-scopes)
