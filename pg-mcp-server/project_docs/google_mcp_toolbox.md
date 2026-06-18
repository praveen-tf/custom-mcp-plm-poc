# Google MCP Toolbox for Databases — Reference Summary

**Source:** https://github.com/googleapis/mcp-toolbox
**Retrieved:** 2026-06-18
**Latest Version:** v1.4.0 (June 4, 2026)
**License:** Apache 2.0

## Overview

The MCP Toolbox for Databases (formerly "Gen AI Toolbox for Databases") is an open-source Go-based MCP server that connects AI agents and applications to enterprise databases (Postgres, MySQL, BigQuery, AlloyDB, Cloud SQL, etc.). It provides pre-built tools, a declarative YAML configuration system for custom tools, and multi-transport support (HTTP, SSE, stdio). **Critical limitation:** designed primarily for BigQuery with strong security controls; Postgres support exists but lacks native column-level whitelisting.

---

## System Architecture & Deployment

### Language & Runtime
- **Primary Language:** Go (v1.21+ or v1.23+)
- **Deployment Models:**
  - **Go Binary:** Compiled standalone binary for Linux AMD64, macOS (Apple Silicon/Intel), Windows AMD64
  - **Docker Container:** Official image published to Google Artifact Registry; uses distroless base for minimal attack surface
  - **NPX/Node.js:** Quick-start via `npx @toolbox-sdk/server` (fetches latest version on run)
  - **Homebrew:** macOS and Linux package management
  - **From Source:** Build directly from Go code
- **Deployment Environments:** Docker hosts, Google Cloud Run, Kubernetes (GKE), any Linux VM

### Transport Protocols
The MCP server supports **multiple transports** for client connections:
- **STDIO (Standard Input/Output):** Local IDE integration (Cursor, Claude Desktop); controlled by `--stdio` flag; reads/writes via stdin/stdout
- **HTTP:** JSON-RPC over HTTP; supports streamable/long-lived connections
- **SSE (Server-Sent Events):** Remote connections over HTTP; marked as deprecated in newer MCP versions

**Network Accessibility:** Yes, the server can run as a **remote MCP server** accessible over HTTP/SSE, enabling integration with ChatGPT connectors and other network clients. Routes defined at `/mcp` and `/mcp/{toolsetName}` for SSE and HTTP POST.

**Note:** Not explicitly optimized for "Streamable HTTP" as a dedicated transport; uses standard HTTP + SSE for long-lived connections.

---

## tools.yaml Configuration Model

### Format Overview
The `tools.yaml` file uses a **flat, declarative format** where each top-level entry declares a `kind` (source, tool, toolset, prompt), a `name`, and type-specific fields. Environment variables supported for sensitive fields (passwords, API keys) with optional defaults.

### Defining Sources
```yaml
kind: source
name: my-postgres
type: postgres
host: 10.0.0.5
port: 5432
database: production_db
user: ${POSTGRES_USER}
password: ${POSTGRES_PASSWORD}
```

Supported types include:
- `postgres` — generic self-hosted PostgreSQL
- `mysql`, `mssql`, `oracle` — other RDBMS
- `cloud-sql-postgres`, `alloydb` — Google Cloud variants
- `bigquery`, `spanner`, `firestore` — Google Analytics/NoSQL
- `mongodb`, `redis`, `elasticsearch`, `neo4j`, `snowflake` — third-party

### Defining Tools
```yaml
kind: tool
name: get_user_profile
type: postgres-sql
source: my-postgres
description: "Fetch user profile by ID"
parameters:
  - name: user_id
    type: string
statement: |
  SELECT id, name, email FROM users WHERE id = $1
```

**Tool Types (Two Main Categories):**

1. **Templated SQL Tools** (e.g., `postgres-sql`, `mysql-sql`):
   - Use a **static `statement`** defined in YAML
   - Receive **structured parameters** from the LLM
   - Support `allowedValues` and `escape` for parameter validation
   - **Maps to your "parameterized query templates" requirement**

2. **Generic Execute Tools** (e.g., `postgres-execute-sql`, `mysql-execute-sql`):
   - Accept **arbitrary SQL string at runtime** from the LLM
   - No built-in table/column filtering at the tool config level
   - **Warning:** explicitly marked "not for production agents" due to security risks (prompt injection, data poisoning)
   - For BigQuery: `bigquery-execute-sql` offers **`allowedDatasets` restriction** (dry-run validation); **Postgres has no equivalent**

3. **Prebuilt Observability Tools** (e.g., `postgres-list-tables`, `mysql-list-tables`):
   - Hardcoded SQL statements; require only `source` specification
   - Used for schema introspection

### Defining Toolsets
```yaml
kind: toolset
name: analytics
tools:
  - get_user_profile
  - list_tables
  - check_queries
```

Groups multiple tools for easier management and MCP export.

---

## Column-Level Whitelisting & Field Security

### ❌ **Native Column Whitelisting: NOT SUPPORTED for Postgres**

**Key Finding:** The MCP Toolbox does **NOT provide native column-level whitelisting that hides sensitive columns from the advertised schema.** 

- For **BigQuery**, dataset-level restrictions exist (`allowedDatasets`), but no column filtering
- For **Postgres/MySQL**, there is **zero built-in column allowlisting** at the tool or schema level
- Column information is retrieved via `list_tables` tools and exposed as-is to the LLM

### ⚠️ **Possible Workarounds (Application-Level)**

1. **Pre-Processing Hook:** Intercept LLM queries before tool invocation and validate SQL against a custom allowlist (application responsibility, not Toolbox)
2. **Parameterized Secure Views (PSVs):** For AlloyDB only; use database-level views with mandatory parameters for row-level access control (does NOT hide columns, only filters rows)
3. **Custom Tool Wrapper:** Write a custom Go tool implementing the `Tool` interface with built-in column filtering (requires Go code modification)

**Verdict on Requirement 1:** This is a significant gap. Building bespoke column whitelisting would require either custom Go code or application-level orchestration logic external to the Toolbox.

---

## Query Execution & Validation

### Generic Open-Ended Query Tool
**Yes, exists:** `postgres-execute-sql` and similar tools allow the LLM to write arbitrary SQL at runtime.

### ⚠️ **Validation Constraints: Limited**

- **For Postgres/MySQL:** No built-in table/column allowlisting; the tool accepts any valid SQL
- **For BigQuery:** `allowedDatasets` configuration on the source **validates at runtime** via dry-run analysis; rejects queries accessing tables outside the allowlist
- **Postgres Variant:** The `postgres-sql` templated tool supports `allowedValues` for parameter validation and `escape` for string injection mitigation, but this is parameter-level, not query-level

### Extensibility for Validation
The Toolbox is designed to be **extended via custom Go implementations** of the `Tool` interface, allowing you to:
- Implement custom SQL parsing and AST validation
- Enforce field-level allowlists
- Add semantic validation before query execution

**But:** This requires **fork + custom Go code**, not pure configuration.

**Verdict on Requirement 3 (constrained open-query mode):** Postgres does not provide built-in query validation like BigQuery does. You would need to implement AST-based validation logic either in a custom Go tool or in an orchestration layer (LangChain, LangGraph, etc.).

---

## Authentication & Authorization

### Supported Methods

**Client-to-Server (Tool Invocation Auth):**
- **Generic OpenID Connect (OIDC):** Integrates with any OIDC-compliant identity provider; validates JWT signatures via JWKS, audience (`aud`), and expiration claims
- **Google Sign-In (OAuth 2.0):** Google-specific OAuth flow with `clientId` validation
- **API Key:** Static key passed in custom header (default `X-API-Key`)
- **HTTP Bearer Token:** Manual static bearer token
- **Application Default Credentials (ADC):** For Google Cloud environments (Cloud Run, GKE) and local `gcloud auth login`

**Database Authentication (Source-Level):**
- Password (plaintext or via env var)
- IAM via ADC (Google Cloud)
- Service account keys

### OAuth 2.1 Support
- **Explicitly listed:** OAuth 2.0 (not 2.1 by name)
- **OIDC Support:** Yes, generic OIDC allows integration with any OIDC-compliant provider
- **Token Types:** JWT and opaque tokens (with introspection)
- **Scopes & Audience:** Configurable validation

**Assessment:** The OIDC/OAuth 2.0 support is flexible and standards-based, likely compatible with ChatGPT Enterprise connector auth requirements (which typically demand OAuth 2.x + OIDC). However, **explicit OAuth 2.1 support is not called out**; you would need to verify ChatGPT's exact requirements (grant types, token formats, claims) against Toolbox's OIDC capabilities.

**Verdict on Requirement 4 (OAuth 2.1):** ⚠️ **Likely sufficient but not explicitly validated.** OIDC support is solid, but OAuth 2.1 is not mentioned by version. Recommend confirming with ChatGPT's connector spec.

---

## PostgreSQL Support

### Self-Hosted Postgres: ✅ **Fully Supported**

The Toolbox supports **generic self-hosted PostgreSQL on any VM:**

```yaml
kind: source
name: my-postgres
type: postgres
host: <vm-ip-address>
port: 5432
database: production_db
user: ${PG_USER}
password: ${PG_PASSWORD}
```

- Supports any PostgreSQL instance reachable via TCP
- No dependency on Google Cloud SQL or managed services
- Tools available: `postgres-execute-sql`, `postgres-sql`, `postgres-list-tables`, `postgres-list-active-queries`, `postgres-long-running-transactions`

### Google Cloud Variants
- **Cloud SQL for PostgreSQL:** `kind: cloud-sql-postgres` (requires project, region, instance fields)
- **AlloyDB for PostgreSQL:** Via generic `postgres` type or dedicated `alloydb` extension

**Verdict on Requirement 6:** ✅ Self-hosted Postgres on a VM is fully supported.

---

## Extensibility & Customization

### Configuration-Level Extensibility

1. **Custom Tools in YAML:** Define new tools by specifying `type`, `source`, `parameters`, and SQL `statement` without code
2. **Pre- and Post-Processing Hooks:**
   - **Pre-processing:** Intercept and sanitize tool inputs; enforce business rules; validate against prompt injection
   - **Post-processing:** Format outputs; redact sensitive fields; audit logs
   - Typically implemented in orchestration frameworks (LangChain, LangGraph, Agent Builder) wrapping the Toolbox

### Code-Level Extensibility

1. **Custom Sources:** Implement `SourceConfig` and `Source` interfaces to add new database types
2. **Custom Tools:** Implement `ToolConfig` and `Tool` interfaces to add custom execution logic
3. **Plugins:** Toolbox is designed as a framework for extending; no formal plugin system, but the Go interfaces are extensible

### Column Whitelisting & SQL Validation via Extensibility

**Realistic Extensibility:**
- ⚠️ Column filtering is **not available without custom Go code**
- Field-level whitelisting would require:
  - A custom Go tool that intercepts `list_tables` output and filters columns
  - Or a custom `postgres-execute-sql` variant that parses and validates SQL against a whitelist
- SQL AST validation is **possible but non-trivial**; you would need to:
  - Implement custom validation logic in a Go tool wrapper
  - Or rely on orchestration framework middleware (e.g., LangChain pre-processing)

**Verdict on Extensibility:** ⚠️ **Moderate.** Configuration is flexible (custom tools, YAML-driven), but custom security logic (column filtering, SQL AST validation) requires Go code contribution or an orchestration layer. Not a "no-fork" solution for these requirements.

---

## SDK Integration & Language Support

- **Python SDK:** Yes (via LlamaIndex, ADK, LangChain integration)
- **JavaScript/TypeScript SDK:** Yes
- **Go SDK:** Yes
- **Java SDK:** Yes

All SDKs connect to the Toolbox server via HTTP/MCP protocol.

**Note:** Toolbox itself is Go-based, not Python. If you require a Python-native implementation, Toolbox requires running a separate Go server process and communicating via HTTP/MCP.

---

## Feature Coverage Table

| Requirement | Status | Notes |
|---|---|---|
| **1. Column-level whitelisting (hide sensitive fields from LLM schema)** | ❌ | No native support for Postgres. BigQuery has dataset-level restrictions only. Requires custom Go tool or orchestration layer pre-processing. |
| **2. Parameterized query templates** | ✅ | `postgres-sql` templated tools with structured parameters; `allowedValues` and `escape` options supported. |
| **3. Constrained open-query mode (validate SELECT against allowlist)** | ⚠️ Partial | `postgres-execute-sql` exists but has **no built-in table/column validation** (unlike BigQuery's `allowedDatasets`). Requires application-level AST validation. |
| **4. ChatGPT Enterprise connector (Streamable HTTP + OAuth 2.1)** | ⚠️ Partial | HTTP/SSE transport supported; OIDC/OAuth 2.0 supported. OAuth 2.1 not explicitly stated; OIDC flexibility likely sufficient but unconfirmed. |
| **5. Python runtime** | ⚠️ Partial | Go-based server; Python SDKs available for client integration. Requires separate Go binary/container process. |
| **6. Self-hosted Postgres on VM (generic postgres source)** | ✅ | Full support via `type: postgres` in tools.yaml; works with any TCP-reachable instance. |
| **7. Extensibility (custom logic without fork)** | ⚠️ Partial | YAML configuration is extensible; pre/post-processing hooks available. Column filtering & SQL validation require Go code or orchestration wrapper. |

---

## Deployment on Azure

The Toolbox can be deployed on Azure via:
- **Azure Container Apps:** Run the Docker container
- **Azure VMs:** Deploy Go binary or Docker
- **Azure Key Vault:** Store database credentials and OIDC secrets
- **Managed networking:** Use vnet/network rules to connect to self-hosted Postgres on your VM

Requires external orchestration (e.g., Python LangChain agent) to handle pre-processing validation and column filtering.

---

## Known Limitations & Gotchas

1. **No Native Column Whitelisting for Postgres:** Unlike BigQuery, Postgres/MySQL have no built-in column filtering. Sensitive column names are exposed in schema metadata.
2. **Generic Execute Tools Not for Production:** `postgres-execute-sql` is explicitly documented as unsafe for autonomous agents; prone to prompt injection and data poisoning.
3. **OAuth 2.1 Not Explicitly Stated:** Toolbox lists OAuth 2.0 and OIDC; OAuth 2.1 compatibility is inferred but not verified.
4. **Requires Separate Go Process:** If your app is pure Python, you still need to run the Go Toolbox server separately (e.g., as a container sidecar).
5. **BigQuery-Centric Security:** Most built-in guardrails (dataset restrictions, parameterized views) are optimized for BigQuery; Postgres support is functional but less secure out-of-the-box.

---

## Verdict

### **BUILD-vs-ADOPT Decision: `adopt-with-config`**

**Reasoning:**

1. **Why Adopt:** The Toolbox provides solid foundations for MCP + multi-transport support, templated query tools, and flexible YAML-driven configuration. Self-hosted Postgres is fully supported. Go binary is lightweight and deployable on Azure.

2. **Why NOT Adopt Wholesale:** Column-level whitelisting (your primary security requirement) is **missing for Postgres**. Generic `postgres-execute-sql` lacks built-in query validation. Requires orchestration layer (Python LangChain/LangGraph) to enforce field filtering and SQL AST validation.

3. **Recommended Approach:**
   - **Use Toolbox for:** MCP transport layer, schema introspection (`postgres-list-tables`), parameterized templated queries (`postgres-sql` tools)
   - **Build Custom:** Python orchestration layer on top that implements column whitelisting, SQL validation, and ChatGPT connector auth
   - **Or:** Forgo Toolbox and build a bespoke Python MCP server (simpler if security constraints are non-negotiable)

**Bottom Line:** Toolbox is a solid foundation for the MCP + Postgres plumbing, but you will **still need custom logic (Go extensions or Python orchestration) to meet your column-filtering requirement**. If simplicity and full Python control matter more than using a third-party framework, building bespoke may be faster.

---

## Sources

- [Google MCP Toolbox Repository](https://github.com/googleapis/mcp-toolbox)
- [MCP Toolbox Releases (v1.4.0, June 4, 2026)](https://github.com/googleapis/mcp-toolbox/releases)
- [PostgreSQL Source Documentation](https://googleapis.github.io/genai-toolbox/resources/sources/postgres/)
- [Cloud SQL for PostgreSQL with MCP Toolbox](https://docs.cloud.google.com/sql/docs/postgres/pre-built-tools-with-mcp-toolbox)
- [MCP Toolbox Quickstart](https://googleapis.github.io/genai-toolbox/getting-started/mcp_quickstart/)
- [Google Cloud Blog: MCP Toolbox for Databases Announcement](https://cloud.google.com/blog/products/ai-machine-learning/mcp-toolbox-for-databases-now-supports-model-context-protocol)
- [MCP Toolbox on Augment Code](https://www.augmentcode.com/mcp/genai-toolbox)
