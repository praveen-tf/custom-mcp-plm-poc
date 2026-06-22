# 004 ChatGPT Business Connector via FastMCP Azure OAuth Proxy

**Status:** draft
**Created:** 2026-06-22
**Last updated:** 2026-06-22

---

## 1. Overview

Connect Several Millers' **ChatGPT Business** workspace to `pg-mcp-server` so the model can query
the Postgres database hosted on the Azure VM. ChatGPT Business's developer-mode MCP connector uses
**OAuth discovery** — it reads OAuth metadata *from the server* and registers itself via DCR/CIMD +
PKCE — so spec 002's two-app "paste Client ID/Secret" pattern does not apply. Instead the server
gains a **FastMCP `AzureProvider`** (an OAuth proxy) that publishes the discovery/registration
endpoints ChatGPT expects and proxies login to a **single** Microsoft Entra app registration. The
server deploys to **Azure Container Apps** (public HTTPS) and reaches the VM's Postgres over the VNet.

This **supersedes spec 002's auth + connector approach** (two-app, Enterprise) and **reuses spec 003's**
VM Postgres + synthetic data + `mcp_readonly` role for the database side.

## 2. Requirements

- WHEN the `AzureProvider` env vars are set, THEN `build_auth()` returns an `AzureProvider` and the
  server publishes `/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`,
  `/register`, `/authorize`, `/token`, and a JWKS endpoint.
- WHEN none of the OAuth vars are set, THEN behavior is unchanged: `JWTVerifier` if the legacy
  issuer/JWKS/audience vars are set, otherwise no-auth (dev) — spec 003 still works.
- WHEN ChatGPT Business "New App" is pointed at `https://<host>/mcp` with **Authentication = OAuth**,
  THEN it **discovers** the OAuth settings, registers a client, and runs auth-code + PKCE(S256) against
  Entra via the proxy.
- WHEN a user completes the Entra login, THEN the proxy mints a FastMCP JWT; every MCP tool call
  carries it; the server validates it and queries Postgres as `mcp_readonly`.
- WHEN the connector is tested in Developer Mode, THEN ChatGPT lists the tools
  (`list_accessible_tables`, `describe_table`, `query`, `get_style_by_code`, `list_styles_in_collection`)
  and a real query returns synthetic rows, while the non-whitelisted column stays unreachable.
- WHEN `curl https://<host>/mcp/` is sent without a token, THEN the server responds **401** and the
  log shows `OAuth enabled`.

### Out of Scope

- The spec 002 two-app pattern and the Enterprise connector flow (replaced here).
- Real PLM data (use the spec 003 synthetic fixture) and production hardening (autoscale, custom
  domain/cert, secret rotation, multi-replica shared client storage / stable signing key beyond the note in C/B).
- Read/write tools — the server stays read-only.

## 3. Design

```
ChatGPT Business "New App" (Server URL https://<host>/mcp, OAuth → discovers) ──┐
   │ DCR/CIMD + PKCE(S256)                                                       │
   ▼                                                                             │
FastMCP AzureProvider on pg-mcp-server  (Azure Container Apps, public HTTPS)     │
   • publishes /.well-known/* + /register + /authorize + /token + JWKS           │
   • proxies login upstream to Entra (ONE app registration: client_id + secret)  │
   ▼                                                                             │
Microsoft Entra ID ── user login, v2 token ──▶ proxy ──▶ FastMCP mints its JWT ──┘
   │
pg-mcp-server validates the JWT → queries Postgres on the VM as mcp_readonly (private VNet)
```

### Affected Files

| Layer | File | Change |
|-------|------|--------|
| Config | `pg-mcp-server/config.py` | Add `oauth_client_id`, `oauth_client_secret`, `oauth_tenant_id`, `oauth_base_url`, `oauth_identifier_uri` (opt), `oauth_jwt_signing_key` (opt). Reuse `oauth_required_scopes`. |
| Auth | `pg-mcp-server/auth.py` | `build_auth()` returns `AzureProvider` when the proxy vars are set; else falls back to today's `JWTVerifier` / `None`. |
| Config sample | `pg-mcp-server/.env.example` | Document the new `PGMCP_OAUTH_*` proxy vars. |
| Tests | `pg-mcp-server/tests/test_auth.py` | Cases: proxy vars → `AzureProvider`; legacy vars → `JWTVerifier`; none → `None`. |
| Deploy | `pg-mcp-server/project_docs/azure_vm_test_deploy_runbook.md` | (companion runbook updated for the Container Apps + Entra single-app path) |

### Key Decisions

- **`AzureProvider`, not two-app.** ChatGPT discovers OAuth from the server (verified: the "New App"
  form only takes a Server URL + OAuth, with *discovered* settings). Entra can't do open DCR, so the
  FastMCP proxy bridges it with one fixed Entra app. Verified API present in `fastmcp 3.4.2`.
- **`base_url` must equal the public host exactly** (`https://<app>.<region>.azurecontainerapps.io`,
  no trailing slash). The connector URL is `<base_url>/mcp`; the Entra redirect URI is
  `<base_url>` + the provider's callback path (default `/auth/callback` — confirm at runtime).
- **Contributor-friendly secrets.** Store the DB URL and the OAuth client secret as **plain Container
  App secrets**, or use **Key Vault on the access-policy model** (the user is Contributor on
  `Several_Millers_Default`, so no RBAC role assignments). ACR pull via **admin user**. See [[sm-deploy-access-constraints]].
- **Business connector is immutable after publish** — to change the URL/OAuth you delete + recreate.
  Pick the path (`/mcp`) and host before publishing.
- **Backward compatible.** No OAuth vars → unchanged; spec 003's no-auth local test keeps working.

## 4. Reference Documents

> Rule: read these before executing; do not duplicate their content here.

| Document | Location | What to look for |
|----------|----------|------------------|
| FastMCP Azure OAuth proxy | `pg-mcp-server/project_docs/fastmcp_oauth_proxy_entra.md` | `AzureProvider` args, exposed endpoints, callback path, the `auth.py` wiring, single-app Entra setup |
| ChatGPT Business connectors | `pg-mcp-server/project_docs/chatgpt_business_mcp_connectors.md` | Discovery/DCR/CIMD flow, Developer Mode gating, no-update-after-publish caveat |
| Container Apps deploy | `pg-mcp-server/project_docs/azure_container_apps_deploy.md` | ACR build, VNet subnet delegation, NSG to VM 5432, public ingress on :8000, plain secrets |
| Entra app registration | `pg-mcp-server/project_docs/entra_id_oauth_app_registration.md` | Expose-an-API `api://<id>`, scope, `requestedAccessTokenVersion=2`, client secret (note: single app here, not two) |
| VM Postgres + synthetic data | `specs/003-several-millers-test-deploy.md` | Provision Postgres on the VM, load `synthetic_load.sql`, create `mcp_readonly` |
| Spec 002 (superseded auth) | `specs/002-azure-entra-deploy-runbook.md` | Container Apps/VNet topology reused; its Entra two-app + Enterprise connector are replaced here |

## 5. Implementation Checklist

Phased; Azure/Entra changes can take ~1 min to propagate. Each task ends with a **Verify**.

### Phase A — Server: add the AzureProvider auth path *(code; do first, locally)*

- [ ] **A1: Config vars** — `config.py`
      Add `oauth_client_id/secret/tenant_id/base_url` (all `str | None = None`), `oauth_identifier_uri`
      and `oauth_jwt_signing_key` (optional). Keep `oauth_required_scopes` (default `["pg.read"]`).
      Verify: `uv run python -c "from config import Settings"` imports clean.

- [ ] **A2: `build_auth()` branch** — `auth.py` *(depends on: A1)*
      If `client_id and client_secret and tenant_id and base_url` are set → return
      `AzureProvider(client_id=…, client_secret=…, tenant_id=…, base_url=…, required_scopes=…,
      identifier_uri=…, jwt_signing_key=…)` and log `OAuth enabled (Azure proxy)`. Else keep the
      existing `JWTVerifier` / `None` logic. Ref: `project_docs/fastmcp_oauth_proxy_entra.md`.
      Verify: with proxy env vars set, `build_auth(get_settings())` returns an `AzureProvider`.

- [ ] **A3: Tests** — `tests/test_auth.py` *(depends on: A2)*
      Cases: proxy vars → `AzureProvider`; legacy issuer/jwks/audience → `JWTVerifier`; none → `None`.
      Verify: `uv run pytest tests/test_auth.py` passes; `ruff` + `mypy` clean.

- [ ] **A4: Sample + docs** — `.env.example`
      Document the new `PGMCP_OAUTH_*` proxy vars with an Entra example.
      Verify: `.env.example` lists every new var.

- [ ] **A5: Local smoke of discovery** *(depends on: A2)*
      Run the server with the proxy vars (a tunnel/ngrok URL as `base_url`) and
      `curl http://127.0.0.1:8000/.well-known/oauth-protected-resource`.
      Verify: returns JSON with `authorization_servers` + `resource`; log shows `OAuth enabled`.

### Phase B — Azure infra (resource group `Several_Millers_Default`)

- [ ] **B1: VM Postgres + synthetic data + role** — follow `specs/003` + the VM runbook
      Verify: `SELECT count(*) FROM centric_8_plm.styles;` returns the generated count; `mcp_readonly`
      reads but cannot write.

- [ ] **B2: ACR + build image** *(Contributor; admin user for pull)*
      Create a Container Registry (Basic) in the RG; `az acr build -r <ACR> -t pg-mcp-server:latest .`.
      Verify: repository shows `pg-mcp-server:latest`.

- [ ] **B3: Delegated subnet + NSG** *(depends on: VM VNet)*
      Add an `aca-infra` `/27` subnet delegated to `Microsoft.App/environments`; NSG inbound allow
      that CIDR → VM `5432`. Ref: `project_docs/azure_container_apps_deploy.md`.
      Verify: subnet shows the delegation; NSG lists the rule.

- [ ] **B4: Container Apps Environment (VNet, external ingress)** *(depends on: B3)*
      Workload-profiles env in the RG, your VNet + `aca-infra`, Virtual IP = External.
      Verify: env provisions and shows the VNet + subnet.

- [ ] **B5: Container App + secrets + env vars** *(depends on: B2, B4; client secret from C1)*
      App `pg-mcp-server` from ACR (`latest`, admin-user pull), ingress from anywhere, **target port 8000**.
      Secrets (plain or Key Vault access-policy): `database-url`, `oauth-client-secret`. Env vars:
      `PGMCP_DATABASE_URL`(→secret), `PGMCP_HOST=0.0.0.0`, `PGMCP_OAUTH_CLIENT_ID`,
      `PGMCP_OAUTH_CLIENT_SECRET`(→secret), `PGMCP_OAUTH_TENANT_ID`, `PGMCP_OAUTH_BASE_URL=https://<APP_HOST>`.
      Verify: latest revision Running; Overview shows the Application Url; log shows `OAuth enabled` +
      `policy validated against DB: 5 tables, 2 templates`; `curl -i https://<APP_HOST>/mcp/` → **401**.

### Phase C — Entra (single app registration) *(Cloud App Admin; self-serve)*

- [ ] **C1: Register the app + expose the scope + redirect URI**
      New registration (note client ID + tenant ID). Expose an API → `api://<client-id>` → scope
      `pg.read`. Manifest `requestedAccessTokenVersion=2`. New client secret (copy). Authentication →
      Web → Redirect URI = `https://<APP_HOST>` + the proxy callback path (default `/auth/callback`;
      confirm from the running server's metadata). Grant admin consent for `pg.read`.
      Feed `client-id`/`secret`/`tenant-id` into B5. Ref: `project_docs/fastmcp_oauth_proxy_entra.md`.
      Verify: manifest shows `requestedAccessTokenVersion: 2` + the `pg.read` scope; consent Granted.

### Phase D — ChatGPT Business connector

- [ ] **D1: Create + test the connector** *(depends on: B5, C1)*
      Settings → Apps & Connectors → Developer mode → **Create**: name, **Server URL** `https://<APP_HOST>/mcp`,
      **Authentication = OAuth** → let it **discover**; review Advanced OAuth settings; check "I understand"
      → Create. Open a Developer-mode chat, select the connector, complete the Entra login.
      Verify: ChatGPT lists all 5 tools; "list accessible tables" + a real `query`/`get_style_by_code`
      return synthetic rows; the non-whitelisted column is unreachable.

- [ ] **D2: Publish for the workspace** *(admin; depends on: D1)*
      Workspace Settings → Apps → Drafts → Publish. (Immutable after publish — recreate to change.)
      Verify: members see the connector in their Apps list.

## 6. Acceptance Criteria

- [ ] `build_auth()` returns `AzureProvider` with the proxy vars set, `JWTVerifier` with the legacy
      vars, `None` with neither; `pytest`, `ruff`, `mypy` clean.
- [ ] The deployed app serves `/.well-known/oauth-protected-resource`; `curl -i https://<APP_HOST>/mcp/`
      without a token returns 401 and the log shows `OAuth enabled`.
- [ ] A single Entra app registration exists with `api://<id>/pg.read`, `requestedAccessTokenVersion=2`,
      a client secret, and the proxy redirect URI; admin consent granted.
- [ ] In ChatGPT Business, the OAuth connector **discovers** settings, login succeeds, all 5 tools list,
      a real query returns synthetic rows, and the non-whitelisted column stays unreachable.
- [ ] The whole path was built with the operator's existing access (Contributor on the RG + Cloud App
      Admin) — no role-assignment or admin hand-off required.
