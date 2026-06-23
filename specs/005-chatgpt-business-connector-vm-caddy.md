# 005 ChatGPT Business Connector — Server on the VM + Caddy (as-built)

**Status:** complete
**Created:** 2026-06-23
**Last updated:** 2026-06-23

---

## 1. Overview

Connects Several Millers' **ChatGPT Business** workspace to the Postgres database on the Azure VM by
running `pg-mcp-server` **directly on the VM**, fronted by **Caddy** (automatic HTTPS), using the
FastMCP **`AzureProvider`** OAuth proxy and a **single Entra app registration**. This is the
**as-built** path that was actually completed; it replaces spec 004's Azure Container Apps plan, which
was **blocked**: the operator is Contributor on the resource group only and **cannot register the
`Microsoft.App` resource provider** (a subscription-level action). Reuses spec 003 (VM Postgres +
synthetic data + `mcp_readonly`) and spec 004 Phase A (the `AzureProvider` server code).

## 2. Requirements (all met)

- WHEN ChatGPT Business connects to `https://smpgmcp.westus.cloudapp.azure.com/mcp` with OAuth, THEN it
  **discovers** the server's OAuth metadata, registers via DCR (+ PKCE/CIMD), and runs the auth-code flow.
- WHEN a user authenticates, THEN Entra shows the **`pg.read` user-consent** screen; on approval the
  proxy issues a FastMCP JWT, every tool call carries it, and the server queries Postgres as `mcp_readonly`.
- WHEN the server runs, THEN it is bound to **`127.0.0.1:8000`** under **systemd**, and **Caddy** serves
  public **HTTPS :443** with an auto-provisioned Let's Encrypt cert for the `cloudapp.azure.com` hostname.
- WHEN the VM reboots, THEN systemd restarts `pg-mcp-server` and Postgres; the **static private IP** and
  **DNS name** are stable.
- WHEN a request arrives without a valid token, THEN the tools are unreachable (401); only the OAuth
  discovery/registration endpoints are public.

### Out of Scope

- Azure Container Apps (spec 004) — blocked by the provider-registration gap.
- Real PLM data (synthetic only) and production hardening (per-user app assignment, Key Vault, monitoring, WAF).
- Connector "publish to workspace" governance beyond a single user's developer-mode connector.

## 3. Design

```
ChatGPT Business ─OAuth (Entra, scope pg.read)─▶ Caddy :443  (Let's Encrypt auto-TLS)
   smpgmcp.westus.cloudapp.azure.com               │ reverse_proxy → 127.0.0.1:8000
                                                    ▼
                         pg-mcp-server (systemd, FastMCP AzureProxy) ─localhost─▶ Postgres (VM)
                                  │ proxies upstream login to                      mg_dwh / centric_8_plm
                                  ▼  Microsoft Entra (one app registration)        as mcp_readonly (read-only)
```

### Resources / config (as-built)

| Layer | Resource / file | Detail |
|-------|-----------------|--------|
| VM | `vm-pgmcp-test` (West US, RG `Several_Millers_Default`) | Ubuntu 24.04; private IP `10.0.0.4` (static), public `172.185.20.44` |
| DNS | Public-IP DNS label | `smpgmcp.westus.cloudapp.azure.com` (free) |
| Firewall | NSG `vm-pgmcp-test-nsg` | inbound: SSH 22, HTTP 80 (ACME), HTTPS 443 |
| DB | PostgreSQL on the VM | `mg_dwh` / schema `centric_8_plm`; role `mcp_readonly` (column-scoped, read-only); **localhost-only** |
| Proxy | Caddy (`/etc/caddy/Caddyfile`) | `reverse_proxy 127.0.0.1:8000`, automatic HTTPS |
| Server | `pg-mcp-server` (systemd `pg-mcp-server.service`) | `uv run python main.py`, bound `127.0.0.1:8000`, `.env` with `PGMCP_OAUTH_*` |
| Identity | Entra app `pg-mcp-server` | client `e66f762e-…`, scope `api://e66f762e-…/pg.read`, redirect `…/auth/callback`, token v2 |
| Connector | ChatGPT Business developer-mode connector | Server URL `…/mcp`, OAuth (discovered) |

### Key Decisions

- **VM + Caddy, not Container Apps.** Option A needed `Microsoft.App` registered (subscription-level) —
  not grantable to the operator. Running on the VM needs no provider registration; the VM already hosts
  Postgres and the server.
- **Caddy for HTTPS.** ChatGPT requires public HTTPS; Caddy auto-issues/renews a Let's Encrypt cert for
  the free `cloudapp.azure.com` hostname and reverse-proxies to the localhost server — far less work than
  manual certs/nginx.
- **Server on localhost + systemd.** The app binds `127.0.0.1:8000` (only Caddy is public-facing) and runs
  as a managed service that restarts on failure and on reboot.
- **Single Entra app + user consent.** The `AzureProvider` proxy bridges ChatGPT's DCR to one fixed Entra
  app; the `pg.read` scope stays at "Admins and users" so each user consents (no pre-auth / admin-consent).
- **Postgres stays local.** Server → DB over `127.0.0.1`, so no VNet / `pg_hba` / public-5432 exposure is
  needed (unlike the Container Apps path).

## 4. Reference Documents

| Document | Location | What to look for |
|----------|----------|------------------|
| FastMCP Azure OAuth proxy | `pg-mcp-server/project_docs/fastmcp_oauth_proxy_entra.md` | `AzureProvider` args, exposed endpoints, `/auth/callback`, the `auth.py` wiring |
| ChatGPT Business connectors | `pg-mcp-server/project_docs/chatgpt_business_mcp_connectors.md` | Discovery/DCR/CIMD, Developer Mode, consent, no-update-after-publish |
| Entra app registration | `pg-mcp-server/project_docs/entra_id_oauth_app_registration.md` | Expose-an-API `api://<id>`, scope, `requestedAccessTokenVersion=2`, client secret |
| Spec 003 (VM Postgres) | `specs/003-several-millers-test-deploy.md` | Provision Postgres, load `synthetic_load.sql`, `mcp_readonly` |
| Spec 004 (server code + blocked plan) | `specs/004-chatgpt-business-oauth-connector.md` | Phase A `AzureProvider` code; why Container Apps was blocked |

## 5. Implementation Checklist (as-built — all done)

- [x] **Task 1: Server OAuth code (Phase A)** — from spec 004: `auth.py` `build_auth()` returns
      `AzureProvider`; new config vars; `pytest`/`ruff`/`mypy` clean.
- [x] **Task 2: VM Postgres + synthetic data + role** — from spec 003: `mg_dwh.centric_8_plm`, 200 styles,
      `mcp_readonly` read-only.
- [x] **Task 3: Public DNS name** — Public IP → DNS name label `smpgmcp` → `smpgmcp.westus.cloudapp.azure.com`.
- [x] **Task 4: Open 80 + 443** — NSG `vm-pgmcp-test-nsg` inbound allow TCP **80** + **443** from Any.
- [x] **Task 5: Caddy** — install; `/etc/caddy/Caddyfile` = `<host> { reverse_proxy 127.0.0.1:8000 }`;
      reload → Let's Encrypt cert obtained.
- [x] **Task 6: Entra app** — register `pg-mcp-server`; Expose-an-API `api://<client-id>` + scope `pg.read`;
      manifest `requestedAccessTokenVersion=2`; client secret; redirect URI `https://<host>/auth/callback`;
      scope consent = "Admins and users".
- [x] **Task 7: `.env`** — `PGMCP_DATABASE_URL` (`mcp_readonly@127.0.0.1/mg_dwh`), `PGMCP_HOST=127.0.0.1`,
      `PGMCP_OAUTH_CLIENT_ID/SECRET/TENANT_ID`, `PGMCP_OAUTH_BASE_URL=https://<host>`,
      `PGMCP_OAUTH_JWT_SIGNING_KEY`; `chmod 600`.
- [x] **Task 8: systemd service** — `pg-mcp-server.service` runs `uv run python main.py`; `enable --now`;
      `active (running)`.
- [x] **Task 9: ChatGPT connector** — Developer mode → Create → Server URL `https://<host>/mcp`, OAuth
      (discovered) → user consents `pg.read` → tools list; queries return synthetic rows.

## 6. Acceptance Criteria (all met)

- [x] `https://<host>/.well-known/oauth-protected-resource/mcp` and `…/oauth-authorization-server` return
      valid OAuth metadata.
- [x] `systemctl status pg-mcp-server` = **active (running)**; journal shows `OAuth enabled (Azure proxy…)`,
      `policy validated against DB: 5 tables, 2 templates`.
- [x] Caddy serves valid HTTPS for `smpgmcp.westus.cloudapp.azure.com`.
- [x] In ChatGPT Business, the connector discovers OAuth, the user consents to `pg.read`, all 5 tools list,
      and queries (`get_style_by_code('AW-71001-001-001')`, `list_styles_in_collection('ALICE'S ADVENTURES
      IN WONDERLAND')`) return synthetic rows.
- [x] Built entirely with the operator's existing access (RG Contributor + Cloud App Admin) — no
      subscription-level provider registration or admin hand-off.

> Built on the existing `pg-mcp-server` (specs 001/003) and spec 004 Phase A. Supersedes spec 004's
> Phase B–D (Container Apps) as the deployment of record.
