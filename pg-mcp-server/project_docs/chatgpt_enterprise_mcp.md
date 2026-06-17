# Deploying a Custom Python MCP Server into ChatGPT Enterprise

Reference material for the `pg-mcp-server` architecture decision.
Researched June 2026 against OpenAI developer docs, OpenAI Help Center, OpenAI Cookbook, and modelcontextprotocol.io.

> **TL;DR**
> - You need a **remote HTTPS MCP server** (no stdio), exposing **Streamable HTTP** at a `/mcp` endpoint.
> - Auth: **OAuth 2.1 (Authorization Code + PKCE)** with **DCR or CIMD** for client registration; static API keys are **not** accepted; **no-auth** is allowed for read-only public servers.
> - For "Postgres results shown in chat," the right primitive is a **custom MCP connector**, ideally packaged as an **App (Apps SDK)** if you want a rich inline results widget. **Not** a Custom GPT, **not** AgentKit. "Skill" is an Anthropic concept, not relevant here.
> - On ChatGPT **Enterprise**, custom connectors require an **admin/owner to enable Developer Mode + RBAC grant**; connectors are **default-OFF** for Enterprise.

---

## 1. Custom MCP Connectors in ChatGPT (Enterprise)

### Who configures them

| Action | Who | Where |
|---|---|---|
| Enable Developer Mode org-wide / allowlist connectors | Workspace **owner/admin** (Enterprise/Edu: also RBAC-granted devs) | Workspace Settings → Permissions & Roles → Connected Data |
| Create a custom connector | End user (with Developer Mode on) | Settings → Apps & Connectors → Advanced → Developer mode → **Create** |
| Publish an app for the workspace | **Admin/Owner only** | Workspace Settings → Apps → Drafts → Publish |
| Per-action governance (read vs write) | Admin | Admin → Apps → App permissions |

- On **Business/Enterprise/Edu**, Developer Mode is **admin-gated**. Connectors are **default-OFF for Enterprise/Edu** (default-ON for Business).
- Custom MCP connectors are available on **Pro, Plus, Business, Enterprise, Education** (web). **Free is excluded.** As of **Nov 13, 2025**, ChatGPT Apps/connectors are supported across all paid plans incl. Business/Enterprise/Edu.

### Remote server requirement

- **A remote, HTTPS MCP server is required. `stdio` is NOT supported.** "ChatGPT requires HTTPS." The server must be reachable on the public Internet.
- **Local dev:** tunnel via OpenAI's built-in **Secure MCP Tunnel**, **ngrok**, or **Cloudflare Tunnel** to get a public HTTPS URL (e.g. `https://abc123.ngrok.app/mcp`).

### Transport

| Transport | Status for ChatGPT |
|---|---|
| **Streamable HTTP** | ✅ **Recommended.** Expose at `/mcp`. |
| HTTP+SSE | ⚠️ Accepted but **legacy** — deprecated in the MCP spec `2025-03-26` in favor of Streamable HTTP. Use only if you must. |
| stdio | ❌ Not supported for ChatGPT connectors. |

> Direct quote (Apps SDK): *"The protocol is transport agnostic… Apps SDK supports both [SSE and Streamable HTTP], but we recommend Streamable HTTP."* Note: an older API tutorial page still demos `transport="sse"` — that page lags current guidance. **Build new servers on Streamable HTTP.**

### Authentication

| Mechanism | Supported? |
|---|---|
| **OAuth 2.1 (Authorization Code + PKCE / S256)** | ✅ Primary path for authenticated connectors |
| **Dynamic Client Registration (DCR, RFC 7591)** | ✅ Supported (known friction point) |
| **Client ID Metadata Documents (CIMD)** | ✅ Supported; **OpenAI now prefers CIMD** (skips DCR by passing a metadata-doc URL as `client_id`) |
| Token endpoint auth: `none` (public client) or `private_key_jwt` | ✅ |
| **No authentication** | ✅ Allowed for public/read-only servers |
| Static **API keys** | ❌ Not supported |
| Client-credentials / M2M grants, service-account tokens, custom mTLS certs | ❌ Not supported |

**Server-side metadata you must publish when using OAuth:**
- `/.well-known/oauth-authorization-server` (or `/.well-known/openid-configuration`)
- `/.well-known/oauth-protected-resource` — Protected Resource Metadata (PRM): `resource`, `authorization_servers`, `scopes_supported`. The `resource` param must be echoed and land in the token `aud` claim (impersonation guard). No separate "verify your domain with OpenAI" step is required for a private connector.

---

## 2. OpenAI Apps SDK and its relationship to MCP

- **Announced at DevDay, Oct 6, 2025.** Available in preview to Business/Enterprise/Edu since **Nov 13, 2025**. App Directory (public submissions) opened ~**Dec 17–18, 2025**. **Still preview/beta in 2026** (only the external-checkout monetization path is labeled GA).
- **The Apps SDK is built ON MCP.** *"With Apps SDK, MCP is the backbone that keeps server, model, and UI in sync."* Every app **requires an MCP server**.
- **Minimal app server = 3 capabilities:** (1) list tools, (2) call tools (return `structuredContent`), (3) return UI components (an embedded resource rendered in the ChatGPT client).
- **Custom inline UI: YES.** Apps render interactive widgets **inline in the conversation** via an **iframe**:
  - UI templates are HTML resources registered on the MCP server, linked to a tool via **`_meta`** fields.
  - The iframe ↔ ChatGPT host bridge is **JSON-RPC 2.0 over `postMessage`** (`ui/notifications/tool-input`, `ui/notifications/tool-result`).
  - The component receives `structuredContent` and re-renders from it; `window.openai` exposes host capabilities: `requestDisplayMode()` (inline / PiP / fullscreen), `setWidgetState()`, `openExternal()`.
- **Languages:** Node/TypeScript is the featured path; **Python is supported via FastMCP** (see `openai/openai-apps-sdk-examples`).

### App vs. plain MCP connector

| | Plain MCP connector | App (Apps SDK) |
|---|---|---|
| Tools | ✅ | ✅ (built on MCP) |
| Inline custom UI / widgets | ❌ (text-only tool results) | ✅ (iframe widgets) |
| OAuth scaffolding | manual | provided |
| Install friction | end-user must enable **Developer Mode** | published apps install **without** Developer Mode |
| Distribution | private / internal | App Directory (after review) **or** admin "deploy to your team" |

> Note: API-side "connectors" (`connector_id` in the Responses API) are OpenAI-maintained MCP wrappers for popular SaaS (Gmail, Drive, SharePoint, etc.) — distinct from your custom ChatGPT connector (which uses `server_url`).

---

## 3. Custom GPTs vs. Agents/AgentKit vs. Connectors vs. Apps

| Primitive | What it is | Where it lives | Uses MCP? | Surfaces results **inline in ChatGPT chat**? |
|---|---|---|---|---|
| **Custom GPT** (+ GPT Actions) | No-code persona = instructions + knowledge files + optional **Actions** (OpenAPI/REST) | ChatGPT consumer (GPT builder/Store) | ❌ Actions use OpenAPI/REST, not MCP | Text-only; **no inline widget** |
| **Connector (MCP)** | Custom remote MCP server brought into ChatGPT via Developer Mode | ChatGPT (consumer + Enterprise admin); also API | ✅ | ✅ tool results return to chat (read + write/modify, beta) |
| **App (Apps SDK)** | MCP server + auth + **UI components** | ChatGPT consumer surface; admin-gated in Enterprise | ✅ (built on MCP) | ✅ **+ interactive inline widget** |
| **AgentKit / Agent Builder** | Visual builder for multi-step agents + ChatKit + Connector Registry + Evals | **Platform/API**, NOT ChatGPT consumer | ✅ (MCP server nodes) | ❌ runs in **your** product (via API/ChatKit), not inside ChatGPT |

### Recommendation for "query Postgres → show results in chat"

**Build a custom MCP connector. Package it as an App (Apps SDK) if you want a formatted inline results table/widget.**

- Expose tools like `list_tables`, `run_query`, `run_template`. Return rows as `structuredContent`; optionally attach a `_meta` UI widget to render a results table inline.
- The **Apps SDK is the only primitive whose explicit job** is to take structured MCP tool results and **render them inline as visible chat output**.
- A plain connector also surfaces tool results to chat (good enough if a Markdown table is acceptable). Choose Apps SDK only if you need the rich widget.
- **Custom GPT** = wrong (text-only, OpenAPI not MCP). **AgentKit** = wrong surface (lives in your app/API, not ChatGPT chat).

### Is "Skill" relevant?

**No.** "Skills" is an **Anthropic/Claude** packaging concept (`SKILL.md`). It is **not** an established OpenAI/ChatGPT primitive. (OpenAI was *reportedly* testing a Claude-like "Skills" feature ~Jan 2026, unconfirmed.) For ChatGPT Enterprise, the correct terms are **App / Apps SDK / MCP connector**. Do not package the Postgres tool as a "Skill."

---

## 4. `search` + `fetch` requirement — depends on context

| Context | Tool requirement |
|---|---|
| **Deep Research** (ChatGPT Deep Research mode + Deep Research via API + "company knowledge") | ❗ **MUST implement exactly `search` + `fetch`** (read-only). No other tools usable in that mode. |
| **Developer Mode / normal Chat** | ✅ **Arbitrary tools** (`run_query`, `list_tables`, …). search/fetch **not** required (since Sept 9, 2025). |
| **Apps SDK** | ✅ Arbitrary developer-named, action-oriented tools (`kanban.move_task`). search/fetch contract does **not** apply. |

> *"To work with ChatGPT deep research and company knowledge (and deep research via API), your MCP server should implement two read-only tools: `search` and `fetch`."* The deep-research model *"doesn't support tool calls or MCP servers that don't implement this interface."* Even with Developer Mode on, **Deep Research only uses these two tools.**

**Required Deep Research schemas** (only if you target Deep Research):

```jsonc
// search(query: string)
{ "results": [ { "id": "...", "title": "...", "url": "...", "text": "snippet (optional)" } ] }

// fetch(id: string)
{ "id": "...", "title": "...", "text": "full document content", "url": "...", "metadata": { } }
```
Both returned as `structuredContent` (also JSON-encoded into the MCP text content). `url` powers citations. `require_approval` must be `never` (read-only).

> **For the Postgres use case:** use **Developer Mode / Chat** (or Apps SDK) so you can expose arbitrary tools like `run_query`. Only add `search`/`fetch` if you also want the connector usable inside Deep Research.

---

## 5. Enterprise Gating (hard requirements)

- **Admin/owner must enable Developer Mode** on the workspace; connectors are **default-OFF for Enterprise/Edu**.
- **RBAC**: Enterprise/Edu admins grant Developer Mode to specific users and decide who can access each vetted app. Admins can **disable Developer Mode org-wide** or **allowlist specific connector URLs**.
- **Action governance**: new actions are **disabled by default**; admins choose *Enable all / Only read / Disable*. Write actions require user confirmation by default (honors the `readOnlyHint` tool annotation).
- **No formal pre-publication "app review" for *private* custom connectors** — OpenAI instead surfaces risk warnings (prompt injection, write-action mistakes, malicious servers); trust burden is on admin/developer. (Public App Directory listings *do* go through OpenAI review — separate path.)
- **OAuth not mandatory** (No-Auth / OAuth / Mixed allowed), but action-taking connectors are expected to use OAuth. **No domain-verification step** for private connectors beyond the OAuth PRM resource-identifier check; just a public HTTPS URL.

---

## 6. Minimal Deployment Checklist (Python → ChatGPT Enterprise)

1. **Build the server with FastMCP** (`pip install fastmcp`; OpenAI's docs/examples use FastMCP v2, also bundled in the official `mcp` Python SDK). Define tools with `@mcp.tool` (e.g. `list_tables`, `run_query`, `run_template`). *(Add `search` + `fetch` only if you want Deep Research support.)*
2. **Run over Streamable HTTP:** `mcp.run(transport="http", host="0.0.0.0", port=8000)` → endpoint at `/mcp`.
3. **Public HTTPS URL:** deploy behind TLS (Cloud Run / ECS / Azure / K8s). If proxying via nginx: `proxy_buffering off`, `proxy_read_timeout 300s`, forward `Host` / `X-Forwarded-*`. For local dev, tunnel via ngrok / Cloudflare Tunnel / Secure MCP Tunnel.
4. **Decide auth:** None for quick tests; for production use **OAuth 2.1 (Auth Code + PKCE)**, publish **PRM** at `/.well-known/oauth-protected-resource`, and support **CIMD** (preferred) or **DCR**.
5. **(Enterprise) Get admin enablement:** owner/admin enables connectors + Developer Mode (Workspace Settings → Permissions & Roles → Connected Data) and grants you via RBAC; allowlist the server URL if required. (Remember: Enterprise defaults connectors **OFF**.)
6. **Enable Developer Mode (your account):** Settings → Apps & Connectors → Advanced → toggle **Developer mode**.
7. **Create the connector:** Settings → Connectors → **Create** → Name, Description, Connector URL (`https://.../mcp`), check "I trust this provider", choose auth. ChatGPT should list your advertised tools.
8. **Enable per conversation & test:** composer **+ → Developer mode** (arbitrary tools) or **+ → Deep research** (pick the MCP server). Run a query; confirm tool invocations and that results render in chat.

> For an inline **results widget** instead of plain text: follow the **Apps SDK** path — register an HTML UI resource, link it to `run_query` via `_meta`, render from `structuredContent` in the iframe.

---

## Caveats / recency flags (year = 2026)

- **Help Center pages returned HTTP 403 to automated fetch** (articles `12584461`, `11509118`, `11487775`). Admin/RBAC/gating facts are corroborated via OpenAI search snippets and developer-docs cross-references, but **exact in-product toggle labels should be confirmed live in your tenant**.
- **Developer Mode + full MCP connectors are explicitly beta**; UI paths ("Apps & Connectors" vs "Connectors") and plan availability shifted through late 2025. The **Nov 13, 2025** expansion to all paid plans and the **Dec 17, 2025** "connectors → apps" rename are the latest anchors.
- **CIMD vs DCR is actively evolving** — CIMD is the newer OpenAI-preferred path; DCR remains supported but is a documented friction point.
- The "a Custom GPT can use Actions OR Apps but not both" claim is third-party and **unverified**.

---

## Sources

**OpenAI developer docs**
- https://developers.openai.com/apps-sdk
- https://developers.openai.com/apps-sdk/concepts/mcp-server
- https://developers.openai.com/apps-sdk/build/mcp-server
- https://developers.openai.com/apps-sdk/build/chatgpt-ui
- https://developers.openai.com/apps-sdk/build/auth
- https://developers.openai.com/apps-sdk/build/monetization
- https://developers.openai.com/apps-sdk/build/state-management
- https://developers.openai.com/apps-sdk/concepts/ui-guidelines
- https://developers.openai.com/apps-sdk/plan/tools
- https://developers.openai.com/apps-sdk/quickstart
- https://developers.openai.com/apps-sdk/deploy/connect-chatgpt
- https://developers.openai.com/api/docs/mcp
- https://developers.openai.com/api/docs/guides/developer-mode
- https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- https://developers.openai.com/api/docs/guides/deep-research
- https://developers.openai.com/api/docs/actions/introduction

**OpenAI blog / announcements**
- https://openai.com/index/introducing-apps-in-chatgpt/ (Oct 6, 2025)
- https://openai.com/index/introducing-agentkit/ (Oct 6, 2025)
- https://openai.com/devday/

**OpenAI Help Center** (403 on direct fetch; via search snippets)
- https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt-beta
- https://help.openai.com/en/articles/11509118-admin-controls-security-and-compliance-in-apps-connectors-enterprise-edu-and-business
- https://help.openai.com/en/articles/11487775-connectors-in-chatgpt
- https://help.openai.com/en/articles/12628342-company-knowledge-in-chatgpt-business-enterprise-and-edu

**OpenAI Cookbook / examples**
- https://developers.openai.com/cookbook/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/readme (Jun 25, 2025)
- https://github.com/openai/openai-cookbook/blob/main/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/main.py
- https://github.com/openai/openai-apps-sdk-examples

**Model Context Protocol**
- https://modelcontextprotocol.io/specification/2025-03-26/basic/transports

**FastMCP (Python)**
- https://gofastmcp.com/integrations/chatgpt
- https://gofastmcp.com/deployment/http

**Secondary / corroborating**
- https://www.remote-mcp.com/chatgpt-connectors (Nov 13, 2025 plan note)
- https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/
- https://skywork.ai/blog/apps-in-chatgpt-vs-custom-gpts-gpt-apps-2025-comparison/
- https://www.bleepingcomputer.com/news/artificial-intelligence/openai-is-reportedly-testing-claude-like-skills-for-chatgpt/
