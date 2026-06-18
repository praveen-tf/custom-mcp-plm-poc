# 002 Azure Deploy + Entra OAuth + ChatGPT Connector Runbook

**Status:** draft
**Created:** 2026-06-18
**Last updated:** 2026-06-18

---

## 1. Overview

This is the operational runbook that takes the already-built `pg-mcp-server` (spec 001)
from a container image to a **live ChatGPT Enterprise connector**. It provisions the read-only
DB role on the Postgres VM, deploys the server to **Azure Container Apps** (VNet-integrated,
public HTTPS) with secrets in **Azure Key Vault**, wires **Microsoft Entra ID** OAuth 2.1 via
the two-app-registration pattern, registers the connector in ChatGPT, and verifies the whole
path end to end. Spec 001 explicitly defers this ("follow-on deploy spec"); this is that spec.

It is a **deployment procedure**, not a code-change spec: the application code already exists
and is unchanged. Most tasks are Azure Portal / Entra / ChatGPT actions, each paired with a
concrete verification.

## 2. Requirements

- WHEN the role SQL is applied on the VM, THEN a `mcp_readonly` login role exists with
  **column-level `SELECT` grants only** and `default_transaction_read_only = on` — no
  table-level grant, no write privilege.
- WHEN `az acr build` finishes, THEN `pg-mcp-server:latest` appears in the registry's repositories.
- WHEN the Container Apps environment is created, THEN it is integrated into the VM's VNet on a
  subnet delegated to `Microsoft.App/environments`, and an NSG rule allows that subnet → VM on TCP 5432.
- WHEN the Container App runs, THEN it pulls `PGMCP_DATABASE_URL` from Key Vault via its
  **system-assigned managed identity** (granted **Key Vault Secrets User**), exposes public HTTPS on
  target port 8000, and the app's `/mcp/` URL is reachable.
- WHEN OAuth env vars are set and a request arrives **without** a valid token, THEN the server returns
  **401** and the log stream shows `OAuth enabled`.
- WHEN Entra is configured, THEN App A (the API) issues **v2.0** access tokens whose `iss` equals
  `PGMCP_OAUTH_ISSUER_URL`, `aud` equals `PGMCP_OAUTH_AUDIENCE` (`api://<appA-client-id>`), and `scp`
  contains `pg.read`; App B (the client) holds a secret and delegated `pg.read` with admin consent.
- WHEN the connector is created in ChatGPT and consent completes, THEN ChatGPT lists the tools
  (`list_accessible_tables`, `describe_table`, `query`, and one tool per template), and a real query
  returns rows while the log stream shows successful per-request token validation.

### Out of Scope

- Any application code change (server logic, tools, policy) — covered by spec 001.
- Production hardening beyond this runbook: autoscale rules, managed-identity **ACR pull** (this
  runbook uses ACR admin user for the Portal path), private DNS, custom domains/certs, WAF, alerting.
- Automating the Entra app registrations or the ChatGPT connector creation (both are manual here).
- Rotating the `mcp_readonly` password / secret lifecycle automation.

## 3. Design

This runbook deploys existing artifacts; it does not modify them. The request path it stands up:

```
ChatGPT ──(OAuth: Entra App B login)──▶ Entra ID ──(v2.0 JWT, aud=api://AppA, scp=pg.read)──▶
  https://<app>.azurecontainerapps.io/mcp/  (Container App, public HTTPS :8000)
    └─ JWTVerifier validates iss/JWKS/aud/scope  ─┐
    └─ PGMCP_DATABASE_URL (Key Vault ref via MSI) ─┴─▶ Postgres VM :5432 (private VNet)  as mcp_readonly
```

### Step 0 — Values to gather first

| Placeholder | What it is | Where |
|-------------|-----------|-------|
| `TENANT_ID` | Entra tenant GUID | Entra admin center → Overview |
| `VM_PRIVATE_IP` | Private IP of the Postgres VM | VM → Networking |
| `DB_NAME` | Target database | (known) |
| `VNET` | The VNet the Postgres VM lives in | VM → Networking |
| `ACR_NAME` | Globally-unique registry name, e.g. `pgmcpacr123` | chosen in Task 2 |
| `appA-client-id` | API app registration's client ID | output of Task 7 |
| `appB-client-id` + secret | Client (ChatGPT) app registration | output of Task 7 |
| `APP_HOST` | Container App public host | Container App → Overview → Application Url |

Fixed names used throughout: RG `pgmcp-rg`, env `pgmcp-env`, app `pg-mcp-server`, delegated subnet
`aca-infra` (free `/27`, e.g. `10.0.8.0/27`), Key Vault secret `pgmcp-database-url`, role `mcp_readonly`.

### Existing artifacts (used, not changed)

| Layer | File | Role in this runbook |
|-------|------|----------------------|
| Script | `pg-mcp-server/scripts/generate_role_sql.py` | Generates `sql/role_setup.sql` from `policy.yaml` (Task 1) |
| SQL | `pg-mcp-server/sql/role_setup.sql` | Applied on the VM to create `mcp_readonly` (Task 1) |
| Container | `pg-mcp-server/Dockerfile` | Built by `az acr build` (Task 2); serves `/mcp/` on 8000 |
| Deploy | `pg-mcp-server/deploy.py` | CLI alternative that scripts `az acr build` + `containerapp create` |
| Config | `pg-mcp-server/config.py` / `.env.example` | Defines the `PGMCP_*` env vars set in Task 6 |
| Auth | `pg-mcp-server/auth.py` | `JWTVerifier` validates issuer/JWKS/audience/`pg.read` (Tasks 6–7) |

### Key Decisions

- **Portal-first, one CLI exception.** All steps are Azure Portal / Entra / ChatGPT clicks except
  `az acr build` (server-side image build, no local Docker). `deploy.py` automates the ACR build +
  `containerapp create` for repeatability, but the Portal path is authoritative here.
- **Two app registrations.** App A is the resource server (only exposes the `pg.read` scope and
  defines the audience); App B is the client ChatGPT logs in as. The server never holds a client
  secret — it only validates tokens (`auth.py` → `JWTVerifier`).
- **v2.0 access tokens are mandatory.** App A's manifest `requestedAccessTokenVersion = 2` forces the
  token `iss`/`aud` to match the v2.0 issuer + `api://` audience the server expects. Skipping it yields
  `iss = sts.windows.net/...` and a 401 — the single most common failure (see Section 4 doc + Task 10).
- **Key Vault uses Azure RBAC.** The human needs **Key Vault Secrets Officer** to create the secret;
  the app's **system-assigned managed identity** needs **Key Vault Secrets User** to read it. Contributor
  alone cannot read/write secrets on an RBAC vault.
- **`/27` delegated subnet** for a Workload-profiles environment; NSG opens only 5432 from that CIDR.

## 4. Reference Documents

> Rule: read these before executing; do not duplicate their content here.

| Document | Location | What to look for |
|----------|----------|------------------|
| Azure Container Apps deploy | `pg-mcp-server/project_docs/azure_container_apps_deploy.md` | ACR build + pull auth, subnet delegation, NSG, VNet env, Key Vault RBAC roles + `keyvaultref` syntax, MSI |
| Entra ID OAuth app regs | `pg-mcp-server/project_docs/entra_id_oauth_app_registration.md` | Two-app pattern, Expose-an-API/scope, `requestedAccessTokenVersion=2`, iss/aud/scp, authorize/token endpoints |
| ChatGPT Enterprise MCP | `pg-mcp-server/project_docs/chatgpt_enterprise_mcp.md` | Custom-connector gating (Developer Mode, RBAC), OAuth fields, Streamable HTTP `/mcp/` |
| Safe Postgres querying | `pg-mcp-server/project_docs/postgres_python_safe_querying.md` | Why column-level GRANTs (never table-level), read-only role |
| Spec 001 | `specs/001-pg-mcp-server.md` | The server this runbook deploys; D4 hosting decision, env vars |

## 5. Implementation Checklist

Ordered; Azure/Entra propagation can take ~1 min between role grants and use. Each task ends with a
**Verify** that must pass before moving on.

- [ ] **Task 1: Create the read-only DB role (on the VM)**
      Files: `pg-mcp-server/scripts/generate_role_sql.py` → `sql/role_setup.sql`
      Details: From `pg-mcp-server/`, `uv run python scripts/generate_role_sql.py > sql/role_setup.sql`,
      review it, set the role password, then `psql -U postgres -d <DB_NAME> -f sql/role_setup.sql`.
      Re-run whenever `policy.yaml` changes. Connection string for Key Vault (Task 5):
      `postgresql://mcp_readonly:<password>@<VM_PRIVATE_IP>:5432/<DB_NAME>?sslmode=require`.
      Verify: in `psql`, `\dp` shows column-level SELECT only (no table-level), `\du` shows
      `mcp_readonly` NOSUPERUSER; connecting as `mcp_readonly` and attempting any `INSERT`/`UPDATE` fails.

- [ ] **Task 2: Container Registry + build the image**
      Details: Portal → Create a resource → **Container Registry** → RG `pgmcp-rg` (new), unique
      `ACR_NAME`, SKU **Basic**. Then from `pg-mcp-server/`: `az acr build -r <ACR_NAME> -t pg-mcp-server:latest .`
      Verify: Container Registry → Repositories shows `pg-mcp-server:latest`.

- [ ] **Task 3: Delegated subnet + NSG rule**
      Details: VNet → Subnets → **+ Subnet** `aca-infra`, free `/27` (e.g. `10.0.8.0/27`), **Subnet
      delegation = `Microsoft.App/environments`**. Then the VM subnet's NSG → Inbound rules → **+ Add**:
      Source = IP Addresses `10.0.8.0/27`, Dest port `5432`, TCP, Allow, Priority `300`.
      Verify: subnet shows the delegation; NSG lists the rule.

- [ ] **Task 4: Container Apps Environment (VNet-integrated)** *(depends on: Task 3)*
      Details: Create a resource → **Container Apps Environment** → name `pgmcp-env`, RG, region, type
      **Workload profiles**. Networking → **Use your own virtual network = Yes** → select `VNET` +
      `aca-infra` → **Virtual IP = External** (public ingress so ChatGPT can reach it).
      Verify: environment provisions successfully and shows the VNet + `aca-infra` subnet.

- [ ] **Task 5: Key Vault + DB secret**
      Details: Create a resource → **Key Vault** → **Permission model = Azure RBAC**. Then Key Vault →
      Access control (IAM) → assign **Key Vault Secrets Officer** to yourself (wait ~1 min). Then Objects
      → Secrets → **+ Generate/Import** → name `pgmcp-database-url`, value = the Task 1 connection string
      (private IP).
      Verify: the secret is created and its value is readable by you (proves the Officer role propagated).

- [ ] **Task 6: Container App + identity + secrets + env vars** *(depends on: Tasks 2,4,5; audience from Task 7)*
      Details:
      6a. Create a resource → **Container App** `pg-mcp-server`, RG, Environment `pgmcp-env`. Container tab:
          uncheck quickstart image → source **Azure Container Registry** → registry/image `pg-mcp-server`/tag
          `latest` (enable ACR **Admin user** for the simplest Portal pull auth). Ingress: Enabled, from
          anywhere, **Target port 8000**.
      6b. Settings → Identity → **System assigned = On**.
      6c. Key Vault → IAM → assign **Key Vault Secrets User** to the `pg-mcp-server` managed identity.
      6d. Container App → Secrets → **+ Add** → key `database-url`, type **Key Vault reference** → vault +
          `pgmcp-database-url`, Identity = System assigned.
      6e. Containers → Edit and deploy → Environment variables (new revision):

      | Name | Source | Value |
      |------|--------|-------|
      | `PGMCP_DATABASE_URL` | Reference a secret | `database-url` |
      | `PGMCP_OAUTH_ISSUER_URL` | Manual | `https://login.microsoftonline.com/<TENANT_ID>/v2.0` |
      | `PGMCP_OAUTH_JWKS_URI` | Manual | `https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys` |
      | `PGMCP_OAUTH_AUDIENCE` | Manual | `api://<appA-client-id>` (from Task 7) |

      Note: `PGMCP_OAUTH_AUDIENCE` needs App A's client ID, so either do Task 7's App A first, or set it
      after Task 7 and roll a new revision. Connector URL = `https://<APP_HOST>/mcp/` (**trailing slash matters**).
      Verify: latest revision is **Running**; Overview shows an Application Url; Log stream shows `OAuth enabled`.

- [ ] **Task 7: Entra ID — two app registrations**
      Details:
      **App A (the API):** App registrations → New registration `pg-mcp-server` (note client ID) → **Expose
      an API** → Application ID URI = default `api://<appA-client-id>` → **Add a scope** `pg.read` (admin +
      user consent) → **Manifest** → `requestedAccessTokenVersion = 2` (forces v2.0 tokens).
      **App B (the client):** New registration `chatgpt-pg-connector` (note client ID) → Certificates &
      secrets → **New client secret** (copy value now) → API permissions → My APIs → `pg-mcp-server` →
      **Delegated** → `pg.read` → **Grant admin consent**. Redirect URI added in Task 9.
      Then ensure `PGMCP_OAUTH_AUDIENCE` = `api://<appA-client-id>` is set in Task 6e.
      Verify: App A manifest shows `requestedAccessTokenVersion: 2` and the `pg.read` scope; App B has a
      secret + delegated `pg.read` with consent **Granted**; `curl -i https://<APP_HOST>/mcp/` returns **401**.

- [ ] **Task 8: Enterprise gating (admin/owner, one-time)**
      Details: Custom connectors are default-OFF on Enterprise. An owner/admin in Workspace Settings →
      Permissions & Roles → **Connected Data** must enable **Developer Mode**, RBAC-grant it to the connector
      user(s), and optionally allowlist the URL.
      Verify: the target user can reach Settings → Connectors → **Create** (custom connector option visible).

- [ ] **Task 9: Create the connector in ChatGPT** *(depends on: Tasks 6,7,8)*
      Details: Settings → Connectors → Create:

      | Field | Value |
      |-------|-------|
      | Connector URL | `https://<APP_HOST>/mcp/` |
      | Authentication | OAuth |
      | Authorization URL | `https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/authorize` |
      | Token URL | `https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token` |
      | Client ID | App B's client ID |
      | Client Secret | App B's secret value |
      | Scopes | `api://<appA-client-id>/pg.read offline_access openid` |

      Copy the redirect/callback URL the form shows → add it as a **Web** redirect URI in App B →
      Authentication → check "I trust this provider" → Create.
      Verify: ChatGPT lists `list_accessible_tables`, `describe_table`, `query`, and one tool per template.

- [ ] **Task 10: Test & verify end to end** *(depends on: Task 9)*
      Details: In ChatGPT: **+ → Developer mode → enable the connector** → complete Entra consent → ask
      "list the accessible tables", then a real query. Watch Container App → Log stream.
      Verify: log stream shows successful token validation per request; results return; the sensitive
      column from spec 001 is still unreachable. If 401 after a valid login, decode the token at **jwt.ms**:
      `iss` must equal `PGMCP_OAUTH_ISSUER_URL` (if it's `sts.windows.net`, App A manifest v2 was missed),
      `aud` must equal `PGMCP_OAUTH_AUDIENCE`, `scp` must contain `pg.read`.

## 6. Acceptance Criteria

- [ ] All checklist tasks done; every per-task **Verify** passed.
- [ ] `mcp_readonly` exists with column-level SELECT only; writes fail at the DB.
- [ ] `pg-mcp-server:latest` is in the registry; the Container App's latest revision is Running with a
      public Application Url and `OAuth enabled` in the log stream.
- [ ] `curl -i https://<APP_HOST>/mcp/` returns 401 without a token.
- [ ] A token minted via App B decodes (jwt.ms) with `iss` = issuer URL, `aud` = `api://<appA-client-id>`,
      `scp` containing `pg.read`.
- [ ] In ChatGPT, the connector lists all tools; "list accessible tables" and a real query succeed, and
      the log stream shows per-request token validation.
- [ ] The spec-001 sensitive column remains unreachable through every tool over the live connector.
- [ ] `project_docs/azure_container_apps_deploy.md` and `project_docs/entra_id_oauth_app_registration.md`
      exist and were used.
