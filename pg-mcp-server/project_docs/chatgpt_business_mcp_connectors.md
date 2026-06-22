# ChatGPT Business Custom MCP Connectors — Reference Summary

**Source:** OpenAI Help Center, OpenAI Developer Docs, OpenAI LinkedIn announcements  
**Retrieved:** 2026-06-22  
**Status:** Generally Available (GA) as of April 2026; full MCP (read+write) in beta

## Overview

ChatGPT Business tier **fully supports custom remote MCP connectors** — both read-only and read+write (write actions are still beta). Your self-hosted MCP server can be connected to a ChatGPT Business workspace via Developer Mode, making tools available to all workspace members. The auth model is OAuth 2.1; no static API keys. This doc is a **Business-specific companion** to `chatgpt_enterprise_mcp.md` — read that doc first for the MCP server architecture (Streamable HTTP, FastMCP, etc.); this doc covers **Business-tier gating, permissions, and limitations**.

---

## 1. Custom MCP Connectors: Does ChatGPT Business Support Them?

**YES. Full support confirmed as of April 2026.**

| Tier | Read/Fetch | Write/Modify | Available | Notes |
|------|---|---|---|---|
| **Plus / Pro** | ✅ | ❌ | Yes (Web only) | Read-only connectors only in Developer Mode |
| **Business** | ✅ | ✅ | Yes (Web only) | **Full MCP (read+write) fully supported, in beta** |
| **Enterprise / Edu** | ✅ | ✅ | Yes (Web only) | Same as Business, plus RBAC granularity |
| **Free** | ❌ | ❌ | No | Not eligible |

**Key point for your project:** ChatGPT Business can connect to a **remote, HTTPS MCP server** and invoke both read operations (query Postgres, fetch rows) and write operations (insert/update/delete). This means your Postgres MCP server's arbitrary tools (`run_query`, `list_tables`, etc.) will work, not just the limited `search`/`fetch` pair.

---

## 2. Admin/Workspace Gating vs. Per-Member Permissions

### Who enables Developer Mode?

**Workspace OWNER/ADMIN only.** There is no granular RBAC for Business — it's a **binary, org-wide toggle**.

- **Location:** Workspace Settings → Permissions & Roles → Connected Data → "Developer mode / Create custom MCP connectors"
- **Scope:** When an admin toggles this ON, it applies org-wide. All workspace members can then create and use custom connectors (no per-member opt-in).
- **Difference from Enterprise:** Enterprise admins can use RBAC to grant Developer Mode to specific users only; Business has no such fine-tuning.

### What does "permission for app creation" enable?

If the user says "I have permission for app creation," that means:
- The workspace admin has **already enabled Developer Mode** org-wide, OR
- The user has been given some elevated workspace role (e.g., admin/owner).

Confirm this by checking: **Settings → Apps & Connectors → Advanced → Developer mode toggle** (should be ON if available).

### Step-by-step: Who does what

| Step | Who | Where | Action |
|---|---|---|---|
| 1. Enable Developer Mode | **Admin/Owner only** | Workspace Settings → Permissions & Roles → Connected Data | Toggle "Developer mode" ON |
| 2. Create a connector | **Any member** (after step 1) | Settings → Apps & Connectors → Advanced → Developer mode | Click "Create"; paste server URL, auth type, etc. |
| 3. Publish for workspace | **Admin/Owner only** | Workspace Settings → Apps → Drafts | Publish connector so all members can see it |
| 4. Use connector | **Any member** | Chat or Deep Research | Select connector in composer |

**Critical difference from Enterprise:** On Business, **app updates are NOT supported after publish**. If you need to change the server URL, tools, or auth settings, you must **delete and recreate the connector**, then republish. Enterprise admins can push updates after publishing.

---

## 3. Authentication: OAuth Required or Optional?

### Supported auth methods

| Method | Support | Notes |
|---|---|---|
| **OAuth 2.1 (Authorization Code + PKCE)** | ✅ **Recommended** | Standard for authenticated connectors; best practice |
| **No Authentication** | ✅ **Allowed** | OK for read-only public servers (e.g., public APIs); not recommended for Postgres |
| **Dynamic Client Registration (DCR)** | ✅ | Supported; known friction point |
| **Client ID Metadata Documents (CIMD)** | ✅ **Preferred by OpenAI** | Newer, cleaner than DCR; pass metadata-doc URL as `client_id` |
| **mTLS (Mutual TLS)** | ✅ | ChatGPT presents OpenAI-managed client cert; you verify at transport layer |
| **Static API keys** | ❌ | Not supported — OAuth is the only dynamic option |
| **Custom headers** | ❌ | Not a first-class option; use OAuth or mTLS |

**For your Postgres server:** You **must use OAuth 2.1** because:
1. The server accesses a private Postgres database.
2. Static API keys are not supported.
3. Each workspace member needs to authenticate their own identity.

### OAuth 2.1 Flow with ChatGPT Business

#### What the connector form asks for

When you create a connector in ChatGPT Settings → Apps & Connectors → Create:

| Field | What it is | Example |
|---|---|---|
| **Connector Name** | User-facing label | "Acme Postgres Connector" |
| **Description** | Short description; optional icon | "Query read-only PLM database" |
| **Server URL** | HTTPS endpoint of your MCP server | `https://mcp-server.azurecontainerapps.io/mcp` |
| **Authentication Type** | Dropdown: "OAuth" or "None" | Select **"OAuth"** |

Once you select "OAuth," ChatGPT **auto-generates** the following and displays it:

| Field | What it is | Auto-generated by ChatGPT? | Your role |
|---|---|---|---|
| **Redirect URI** | Where ChatGPT sends the auth code after user logs in | ✅ Yes, auto-generated | Copy this and register it in your OAuth server |
| **Client ID** | ChatGPT's identity to your OAuth server | Varies | Depends on your auth flow (CIMD vs DCR) |
| **Client Secret** | (if applicable) | Varies | Not typically used in CIMD; used in DCR |

#### CIMD (Client ID Metadata Documents) — Recommended Path

OpenAI's **preferred approach** as of 2026:

1. **Your server publishes a metadata document** at a publicly accessible URL, e.g.:
   ```
   https://mcp-server.azurecontainerapps.io/.well-known/openid-configuration
   ```
   This document includes redirect URIs, scopes, token endpoint, etc.

2. **ChatGPT** discovers and reads this doc; no manual secret exchange.

3. **In ChatGPT connector form:** pass the metadata-doc URL as the `client_id` field (counter-intuitive but correct per OpenAI docs).

#### DCR (Dynamic Client Registration) — Legacy but Still Supported

If your OAuth server doesn't support CIMD:

1. ChatGPT requests a client registration from your server's registration endpoint (RFC 7591).
2. Your server returns a `client_id` and `client_secret`.
3. ChatGPT uses these in the Authorization Code + PKCE flow.

**Known friction:** DCR is more complex to implement and debug; CIMD is simpler. Ask your OAuth provider (Microsoft Entra ID in your case) if it supports CIMD. If not, fall back to DCR.

#### PKCE (Proof Key for Code Exchange)

**Mandatory as of Nov 2025 spec revision.** ChatGPT uses **SHA-256 PKCE (S256)**, not the weaker `plain` method. Your server must validate the PKCE challenge.

### What happens at runtime

1. **User invokes a tool** (e.g., `run_query`) in ChatGPT.
2. ChatGPT launches the **OAuth Authorization Code + PKCE flow**.
3. User is redirected to your **Entra ID login screen**.
4. After login, Entra ID redirects back to ChatGPT with an authorization code.
5. ChatGPT exchanges the code for an **access token**.
6. **Every tool call** includes `Authorization: Bearer <token>` in the MCP request.
7. Your server validates the token (issuer, audience, expiration, scopes) and executes the tool.

### Protected Resource Metadata (PRM)

Your server **must publish metadata** at:
```
/.well-known/oauth-protected-resource
```

This tells ChatGPT:
- Which authorization server to use (`authorization_servers`)
- Supported scopes (`scopes_supported`)
- The `resource` identifier (must echo back in the token `aud` claim for impersonation guard)

**No domain-verification step** is required for private Business connectors; the OAuth token validation is the security boundary.

---

## 4. Connector URL Format & Constraints

### URL format

```
https://mcp-server.azurecontainerapps.io/mcp
```

- **Scheme:** MUST be `https://` (public-facing).
- **Host:** Your Azure Container Apps public endpoint or custom domain.
- **Path:** Typically `/mcp` (by convention; can vary if you proxy differently).
- **Trailing slash:** `/.../mcp/` vs `/.../mcp` — **does NOT matter to ChatGPT** (it's HTTP; server should handle both). For consistency with other MCP server examples, use no trailing slash.

### Transport & protocol

- **Streamable HTTP** (recommended): ChatGPT sends tool calls over HTTP; server responds with streaming JSON.
- **Server-Sent Events (SSE):** Supported but legacy (deprecated in MCP spec 2025-03-26). Use only if you must.
- **stdio:** Not supported for ChatGPT connectors.

### Constraints on tools & schemas

**No published hard limits on:**
- Number of tools (but ~50+ tools is reasonable; thousands may degrade performance).
- Schema size (but keep individual tool descriptions <2KB for clarity).
- Response payload size: **If a tool response exceeds the client's configured limit, the client fails fast and returns a structured error** instead of forwarding to the model. This prevents token bloat.

**For your Postgres use case:** a few query tools (`run_query`, `list_tables`, `run_template`) + read-only actions should have no issues.

---

## 5. Business vs. Enterprise: Key Differences

### Similarities

- ✅ Both support custom remote MCP connectors (OAuth 2.1).
- ✅ Both support full read+write operations (in beta).
- ✅ Both require HTTPS, Streamable HTTP transport.
- ✅ Both support CIMD, DCR, PKCE.
- ✅ Both can use mTLS or OAuth.

### Differences

| Aspect | Business | Enterprise | Impact on Your Deploy |
|---|---|---|---|
| **Developer Mode granularity** | Org-wide toggle (all or nothing) | Per-user via RBAC | If you want to restrict connectors to certain teams on Enterprise, you can. Business is all-or-nothing. |
| **App updates post-publish** | **NOT supported** — must recreate & republish | Supported — admins can change settings after publish | **Major blocker if frequent updates needed.** On Business, iteration = delete + recreate. Plan connector immutability. |
| **Admin action governance** | Binary enable/disable | Fine-grained: "All / Read-only / Disabled" per action | Enterprise admins can restrict write actions by default. Business cannot. |
| **App Directory visibility** | Custom connectors stay private | Can be shared or published to App Directory | Not relevant if staying internal. |
| **Cost** | Lower (~$30–50/user/month) | Higher (~$600–1500/user/month) | For a large team, Business is cost-effective if you accept the limitations. |

### What this means for your spec 002 runbook

**Your current runbook likely says "ChatGPT Enterprise" — here's what to change for Business:**

1. **Update admin enablement:** "On Business, Developer Mode is **org-wide**; there is no per-user RBAC. Admin toggles it on in Workspace Settings → Permissions & Roles → Connected Data."
2. **Update connector updates:** Add a note: "**After publishing on Business, you cannot update the connector in-place.** If the Postgres server URL or OAuth config changes, delete the published connector and recreate it. Plan for connector immutability."
3. **Action governance:** Remove Enterprise-specific per-action enable/disable steps. Business uses a simpler enable/disable model.
4. **Cost note:** Add optional note that Business tier is cheaper than Enterprise if the app-update limitation is acceptable.

---

## 6. Current Limitations & Caveats (2026)

### Beta status

- **Full MCP (write actions) is still beta** as of June 2026, though it was marked "generally available" in April 2026. Expect occasional breaking changes or UI tweaks.
- **Developer Mode UI** is stable but the underlying App/Connector system shifted terminology in Dec 2025 ("Connectors" → "Apps"), though both terms are still used interchangeably in docs.

### Rollout and regional constraints

- **Global rollout:** As of April 2026, custom MCP support is available in ChatGPT web globally for Business+ tiers. No known regional blocks.
- **ChatGPT mobile / API:** MCP connectors are **web-only** for now. If you need API access to your Postgres server, use the Responses API or AgentKit, not ChatGPT connectors.

### Tool-surface gating

- **Developer Mode (normal chat):** Arbitrary tools allowed (no `search`/`fetch` requirement). Your `run_query` tools will work.
- **Deep Research:** Limited to read-only `search` + `fetch`. Postgres write operations cannot be exposed here.
- **Apps (Apps SDK):** Arbitrary tools (like Developer Mode) + custom inline UI widgets. More friction to publish but richer UX.

### CIMD vs DCR friction

- **CIMD (preferred):** Not all OAuth providers support it yet. Microsoft Entra ID has **indirect support via OpenID Connect Discovery** — you can publish an `/.well-known/openid-configuration` and ChatGPT should read it. Confirm with Entra ID docs.
- **DCR (fallback):** Works on most OAuth servers but requires RFC 7591 implementation and a registration endpoint.

### Chat-specific gating

- **Deep Research surface:** Only `search` + `fetch` tools are usable. Arbitrary tools (like `run_query`) will **not** appear in Deep Research mode, even if the connector is enabled.
- **Developer Mode in chat:** Full tool access (no restrictions). This is the surface for your Postgres query tools.

---

## 7. Minimal Deployment Checklist (Business Tier)

1. **Build the MCP server** with FastMCP (Python) or similar. Expose tools like `run_query`, `list_tables`, etc. (not just `search`/`fetch`). Deploy to **Azure Container Apps** with public HTTPS endpoint. See `chatgpt_enterprise_mcp.md` for the full server architecture; it applies here too.

2. **Set up OAuth 2.1 with Entra ID:**
   - Register an app in Entra ID.
   - Configure redirect URI to the ChatGPT-generated callback URL (will get this from the connector form).
   - Publish `/.well-known/oauth-protected-resource` from your MCP server (or Entra ID's `.well-known/openid-configuration`).
   - Support **PKCE (S256)** and **CIMD** (or DCR as fallback).
   - See `entra_id_oauth_app_registration.md` for details.

3. **Workspace admin enables Developer Mode:**
   - Workspace Settings → Permissions & Roles → Connected Data → toggle **Developer mode** ON.
   - Confirm setting persists (it's org-wide, not per-user on Business).

4. **Create the connector:**
   - Your account: Settings → Apps & Connectors → Advanced → Developer mode (toggle ON).
   - Click **Create** → fill in name, description, server URL (`https://.../mcp`), select "OAuth".
   - ChatGPT generates a **Redirect URI** — copy this.
   - If using CIMD: copy the CIMD metadata-doc URL into the `client_id` field.
   - If using DCR: paste the `client_id` and `client_secret` returned by your Entra ID registration.
   - ChatGPT should discover and list your tools.

5. **Test in Developer Mode chat:**
   - New chat → **+ → Developer mode** (if available).
   - Select your connector.
   - Invoke a tool (e.g., `run_query`) and confirm it works.

6. **Workspace admin publishes the connector** (so all members see it):
   - Workspace Settings → Apps → Drafts → find your connector → **Publish**.
   - Once published, members see it as "custom" in their Apps settings.

7. **Update procedures:** If you need to change the server URL or OAuth config later, **delete the published connector and recreate it** (Business limitation). Plan for connector immutability; versioning via `/v1`, `/v2` endpoints is one mitigation.

---

## What This Means for Our Azure Container Apps + Entra OAuth Deploy

### Summary

**ChatGPT Business DOES support custom remote MCP connectors.** The setup is nearly identical to Enterprise, with these **Business-specific caveats:**

1. **Developer Mode is org-wide** (not per-user RBAC). Workspace admin flips one toggle; all members can create/use connectors.

2. **Cannot update after publish.** If you need to change the connector post-launch, recreate it. Plan for semantic versioning or immutable deployments.

3. **OAuth 2.1 is required** (no static API keys). Your Entra ID + PKCE + CIMD/DCR setup is the right path. See `entra_id_oauth_app_registration.md` and `chatgpt_enterprise_mcp.md` for implementation details.

4. **Streamable HTTP /mcp endpoint** on Azure Container Apps (HTTPS, public). No trailing-slash sensitivity. You're good on that front.

5. **Write actions are beta** (as of June 2026), but fully functional for Business tier. Your read+write Postgres tools will work.

6. **No regional or rollout blocks** as of April 2026. You can deploy and connect immediately once the Entra ID OAuth is configured.

### Next steps in your runbook

- Update spec 002 references from "Enterprise" to "Business" (or both, if covering both tier flows).
- Document the **"delete + recreate to update"** limitation explicitly.
- Confirm Entra ID CIMD support with Microsoft; if not available, implement DCR fallback.
- Test the OAuth flow end-to-end in a Business sandbox workspace before production.

---

## Sources

**OpenAI Developer Docs**
- [MCP and Connectors | OpenAI API](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)
- [Authentication – Apps SDK | OpenAI Developers](https://developers.openai.com/apps-sdk/build/auth)
- [ChatGPT Developer mode | OpenAI Developers](https://developers.openai.com/api/docs/guides/developer-mode)
- [Building MCP servers for ChatGPT Apps and API integrations](https://developers.openai.com/api/docs/mcp)

**OpenAI Help Center** (via search snippets; direct fetch returned 403)
- [Developer mode and MCP apps in ChatGPT | OpenAI Help Center](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta)
- [Apps in ChatGPT | OpenAI Help Center](https://help.openai.com/en/articles/11487775-connectors-in-chatgpt)
- [ChatGPT Business - Release Notes | OpenAI Help Center](https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes)
- [Admin Controls, Security, and Compliance in apps (Enterprise, Edu, and Business) | OpenAI Help Center](https://help.openai.com/en/articles/11509118-admin-controls-security-and-compliance-in-apps-enterprise-edu-and-business)

**OpenAI Blog & Announcements**
- [ChatGPT Business, Enterprise, and Edu get MCP support | LinkedIn](https://www.linkedin.com/posts/openai-for-business_introducing-full-mcp-support-for-chatgpt-activity-7385032029874286592-XK8P)
- [Introducing custom deep research connectors via MCP | LinkedIn](https://www.linkedin.com/posts/openai-for-business_yesterday-we-launched-custom-deep-research-activity-7336428401160790016-t6GC)

**Third-party Corroborating Sources**
- [Auth0 Blog: Integrate Your Auth0 Secured MCP Server in ChatGPT](https://auth0.com/blog/add-remote-mcp-server-chatgpt/)
- [ChatGPT MCP: How to Connect Any MCP Server to ChatGPT (2026) | Hjarni Blog](https://hjarni.com/blog/how-to-use-mcp-with-chatgpt)
- [ChatGPT App SDK & MCP Developer Mode MCP - Complete Tutorial | GitHub Gist](https://gist.github.com/ruvnet/7b6843c457822cbcf42fc4aa635eadbb)
- [MCP OAuth 2.1 Authentication: Complete Developer Guide 2026 | RockB](https://baeseokjae.github.io/posts/mcp-oauth-authentication-guide-2026/)
- [Securing MCP Servers with OAuth2: Ory Hydra + Claude Code + ChatGPT | Getlarge Blog](https://getlarge.eu/blog/securing-mcp-servers-with-oauth2-ory-hydra-claude-code-chatgpt/)
- [Remote MCP in the Real World: OAuth 2.1, Dynamic Client Registration, and Protected Resource Metadata | Medium](https://medium.com/@yagmur.sahin/remote-mcp-in-the-real-world-oauth-2-1-9d149de6e475)

**OpenAI Cookbook & Examples**
- [How to build a Deep Research MCP server | OpenAI Cookbook](https://developers.openai.com/cookbook/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/readme)

**Model Context Protocol**
- [MCP Specification 2025-03-26: Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
