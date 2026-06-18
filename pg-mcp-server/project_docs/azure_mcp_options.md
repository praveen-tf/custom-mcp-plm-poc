# Azure MCP Options & Python PostgreSQL MCP Servers — Evaluation for Custom Postgres MCP Server

**Source:** Research of Azure MCP Server, modelcontextprotocol/servers, pgEdge, crystaldba/postgres-mcp, AWS Labs postgres-mcp-server, and community projects  
**Retrieved:** 2026-06-18  
**Context:** Evaluating build-vs-adopt decision for a custom Postgres MCP server with column-level whitelisting, parameterized queries, constrained open-query mode, and ChatGPT Enterprise connector capability (Streamable HTTP + OAuth 2.1)

---

## Project Requirements (7 Key Criteria)

1. **Column-level whitelisting** — Hide sensitive fields (password_hash, PII) from schema the LLM sees
2. **Parameterized query templates** (e.g. `get_user_profile`)
3. **Constrained open-query mode** — Model writes SELECT, server validates against table/column whitelist
4. **ChatGPT Enterprise connector** — Streamable HTTP + OAuth 2.1
5. **Python** — Preferred language
6. **Self-hosted PostgreSQL on VM** — NOT managed Azure Database for PostgreSQL
7. **Deployable on Azure Container Apps**

---

## Candidate Evaluation

### A. Azure MCP Server (`Azure/azure-mcp`)

**Overview:** Microsoft's first-party MCP server for Azure services. Includes PostgreSQL query tools targeting Azure Database for PostgreSQL – Flexible Server (managed).

| Requirement | Status | Note |
|---|---|---|
| **Language** | C# / TypeScript | Not Python |
| **Column whitelisting** | ❌ | No schema filtering; exposes full table schema to LLM |
| **Parameterized templates** | ⚠️ | Supports list/query/schema commands; no explicit template pattern library |
| **Open-query mode** | ⚠️ | `DatabaseQueryCommand` executes arbitrary SQL; no validation against whitelist |
| **ChatGPT connector** | ⚠️ | Supports remote deployment via Azure Container Apps; no explicit OAuth 2.1/Streamable HTTP docs |
| **Self-hosted PostgreSQL** | ❌ | **MANAGED ONLY** — All queries target Azure Database for PostgreSQL – Flexible Server via resource group / server name lookups |
| **Azure deployment** | ✅ | Native Azure integration; documented Container Apps deployment |

**Verdict:** `not-suitable` — Explicitly targets managed Azure Database for PostgreSQL, not self-hosted VMs. No Python. No column whitelisting or schema filtering.

**Sources:**
- [Azure Database for PostgreSQL Tools - Azure MCP Server (learn.microsoft.com, 2026-05-13)](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/azure-database-postgresql)
- [Deep-wiki: Azure/azure-mcp (2026-06-18)](https://deepwiki.com)

---

### B. First-Party Microsoft Azure PostgreSQL MCP Extension

**Finding:** No dedicated "Azure Database for PostgreSQL MCP server" extension exists separate from the general `Azure/azure-mcp` server above. The PostgreSQL support is built directly into the main Azure MCP server and inherits all its limitations.

**Verdict:** Not applicable (no separate product).

---

### C. modelcontextprotocol/servers Archived PostgreSQL Server

**Overview:** TypeScript-based reference MCP server from Anthropic. Now archived (May 2025) in `modelcontextprotocol/servers-archived`; still seeing ~20k weekly NPM downloads.

| Requirement | Status | Note |
|---|---|---|
| **Language** | TypeScript | Not Python |
| **Column whitelisting** | ❌ | No schema filtering mentioned |
| **Parameterized templates** | ❌ | Reference implementation; no template library |
| **Open-query mode** | ✅ | Executes read-only arbitrary queries (no mutation guard) |
| **ChatGPT connector** | ⚠️ | Supports stdio and Docker; unclear Streamable HTTP / OAuth |
| **Self-hosted PostgreSQL** | ✅ | Supports any PostgreSQL (via connection URL); not Azure-specific |
| **Azure deployment** | ⚠️ | Can run in Container Apps but no native integration |
| **Read-only enforcement** | ✅ | All queries run in READ ONLY transaction |

**Verdict:** `borrow-pattern` — Archived reference, TypeScript (not Python), no whitelisting, but demonstrates clean read-only safety model and arbitrary query execution pattern.

**Sources:**
- [modelcontextprotocol/servers-archived (github.com, accessed 2026-06-18)](https://github.com/modelcontextprotocol/servers-archived)
- [Deep-wiki: modelcontextprotocol/servers (2026-06-18)](https://deepwiki.com)

---

### D. crystaldba/postgres-mcp (Postgres MCP Pro)

**Overview:** Popular community Python MCP server (2,000+ GitHub stars). Uses psycopg3 async I/O. Configurable read-only ("Restricted") vs read-write ("Unrestricted") modes.

| Requirement | Status | Note |
|---|---|---|
| **Language** | Python (98.4%) | ✅ |
| **Column whitelisting** | ❌ | No table/column whitelisting capabilities mentioned |
| **Parameterized templates** | ⚠️ | No explicit template library; supports raw query execution |
| **Open-query mode** | ✅ | Executes arbitrary queries (read-only in "Restricted" mode) |
| **ChatGPT connector** | ⚠️ | Supports stdio and SSE (Server-Sent Events); no explicit Streamable HTTP / OAuth 2.1 docs |
| **Self-hosted PostgreSQL** | ✅ | Works with any PostgreSQL instance |
| **Azure deployment** | ✅ | Can run in Container Apps (Docker/Python available) |
| **Read-only enforcement** | ✅ | "Restricted" mode enforces read-only via transaction-level control |

**Verdict:** `use-as-scaffold` — **BEST community starting point.** Python, strong async foundation with psycopg3, read-only mode, and minimal security model. **Missing:** column whitelisting, parameterized templates, explicit ChatGPT OAuth/Streamable HTTP support. Needs custom extension for all 3 proprietary features.

**Sources:**
- [crystaldba/postgres-mcp (github.com)](https://github.com/crystaldba/postgres-mcp)
- [Postgres MCP Pro Server (mcpservers.org)](https://mcpservers.org/servers/crystaldba/postgres-mcp)
- [WebFetch: crystaldba/postgres-mcp README (2026-06-18)](fetched)

---

### E. pgEdge PostgreSQL MCP Server

**Overview:** Production-ready open-source server (general availability April 2026). Supports stdio, HTTP, and TLS. Multi-database support.

| Requirement | Status | Note |
|---|---|---|
| **Language** | Not specified | Likely TypeScript/Node or Python; docs do not clarify |
| **Column whitelisting** | ❌ | No column-level access controls mentioned |
| **Parameterized templates** | ⚠️ | Full schema introspection but no explicit template pattern |
| **Open-query mode** | ✅ | Supports arbitrary query execution |
| **ChatGPT connector** | ⚠️ | Supports HTTP with Bearer token auth; **no OAuth 2.1 / Streamable HTTP mentioned**; works with OpenAI GPT-5 |
| **Self-hosted PostgreSQL** | ✅ | Supports any PostgreSQL instance (via connection pool) |
| **Azure deployment** | ✅ | Can run in Container Apps (Docker available) |
| **Multi-database** | ✅ | Supports dev/staging/prod environments in single server |

**Verdict:** `adopt-with-config` — Production-ready, supports HTTP transport and arbitrary queries, works with self-hosted PostgreSQL. **Gaps:** no Python confirmation, no column whitelisting, no OAuth 2.1 / Streamable HTTP for ChatGPT. Bearer token auth is less modern than OAuth 2.1. Requires custom extension for whitelisting.

**Sources:**
- [Introducing the pgEdge Postgres MCP Server (pgedge.com, 2026)](https://www.pgedge.com/blog/introducing-the-pgedge-postgres-mcp-server)
- [pgEdge Documentation — MCP Protocol (docs.pgedge.com)](https://docs.pgedge.com/pgedge-postgres-mcp-server/development/developers/mcp-protocol/)
- [WebFetch: pgEdge blog + client examples (2026-06-18)](fetched)

---

### F. AWS Labs postgres-mcp-server

**Overview:** Supports Aurora PostgreSQL and Amazon RDS for PostgreSQL via pgwire protocol. Also supports IAM and password authentication. Read-only enforced via blocklist (DML/DDL verbs, session-state statements).

| Requirement | Status | Note |
|---|---|---|
| **Language** | Python (available on PyPI) | ✅ |
| **Column whitelisting** | ❌ | No schema filtering; blocklist is defense-in-depth, not a security boundary |
| **Parameterized templates** | ❌ | No explicit template library |
| **Open-query mode** | ✅ | Converts natural language to SQL; `--allow_write_query` optional |
| **ChatGPT connector** | ⚠️ | Supports stdio (Docker); **no Streamable HTTP / OAuth 2.1 mentioned** |
| **Self-hosted PostgreSQL** | ✅ | Supports Amazon RDS (non-Aurora) via `pgwire` protocol; also supports general self-hosted via pgwire if network-accessible |
| **Azure deployment** | ⚠️ | Runs Docker locally; not Azure-native (AWS-focused) |
| **Read-only enforcement** | ⚠️ | Keyword blocklist (best-effort); recommends using dedicated low-privilege Postgres role for security |

**Verdict:** `borrow-pattern` — Python, read-only mode, supports arbitrary query execution. **Gaps:** AWS-centric (RDS focus, no Azure-native docs), no column whitelisting, no modern OAuth/Streamable HTTP for ChatGPT, blocklist-based security not suitable for production. Not an off-the-shelf fit.

**Sources:**
- [Amazon Aurora Postgres MCP Server (awslabs.github.io/mcp, accessed 2026-06-18)](https://awslabs.github.io/mcp/servers/postgres-mcp-server)
- [AWS Labs postgres-mcp-server README (github.com/awslabs/mcp, main branch)](https://github.com/awslabs/mcp/blob/main/src/postgres-mcp-server/README.md)
- [Supercharging AWS database development with AWS MCP servers (aws.amazon.com/blogs, 2025)](https://aws.amazon.com/blogs/database/supercharging-aws-database-development-with-aws-mcp-servers/)

---

### G. Community Alternatives (Minor Mentions)

**mahdiboughrous/mcp-postgresql** — Python, LangChain + Gemini, read-only via regex filtering, no column whitelisting, no explicit ChatGPT support.

**gldc/mcp-postgres** — Python, supports stdio|sse|streamable-http transports, read-only mode, Google OAuth (not OAuth 2.1), no column whitelisting. **Potentially relevant for transport patterns.**

**postgresql-ssh-mcp (Zlash65)** — Python, SSH tunneling for Claude Desktop and ChatGPT, Streamable HTTP transport, OAuth support (Auth0). **Relevant for SSH tunnel pattern and modern transport.** No column whitelisting.

---

## Comparison Table

| Candidate | Language | Column Whitelisting | Parameterized Templates | Open-Query Mode | ChatGPT Connector (Streamable HTTP + OAuth 2.1) | Self-Hosted PostgreSQL | Azure Deployment | Python | **Verdict** |
|---|---|---|---|---|---|---|---|---|---|
| **Azure/azure-mcp** | C#/TypeScript | ❌ | ⚠️ | ⚠️ | ⚠️ | ❌ (Managed only) | ✅ | ❌ | **not-suitable** |
| **modelcontextprotocol archived** | TypeScript | ❌ | ❌ | ✅ | ⚠️ | ✅ | ⚠️ | ❌ | **borrow-pattern** |
| **crystaldba/postgres-mcp** | ✅ Python | ❌ | ⚠️ | ✅ | ⚠️ (SSE, no OAuth) | ✅ | ✅ | ✅ | **use-as-scaffold** |
| **pgEdge** | Unknown | ❌ | ⚠️ | ✅ | ⚠️ (Bearer token, no OAuth 2.1) | ✅ | ✅ | ❓ | **adopt-with-config** |
| **AWS Labs postgres-mcp-server** | ✅ Python | ❌ | ❌ | ✅ | ⚠️ (Docker/stdio, no OAuth) | ✅ | ⚠️ | ✅ | **borrow-pattern** |
| **gldc/mcp-postgres** | ✅ Python | ❌ | ❌ | ✅ | ✅ (Streamable HTTP) | ✅ | ✅ | ✅ | **borrow-pattern** |

---

## Key Findings

### No Turnkey Solution Exists

**None** of the evaluated servers satisfy all 7 requirements. Specifically:

- **Column-level whitelisting is universally absent.** No evaluated server filters the schema exposed to the LLM to hide sensitive columns (password_hash, PII). This is a **critical gap**; you will need to implement this custom feature regardless of which server you adopt.
- **Parameterized template libraries are absent.** All servers support raw query execution or natural-language-to-SQL translation; none provide a pre-built pattern library for common queries (e.g. `get_user_profile`).
- **ChatGPT OAuth 2.1 + Streamable HTTP support is rare.** pgEdge supports HTTP but only with Bearer tokens, not OAuth 2.1. Only `gldc/mcp-postgres` and the SSH tunnel project document modern transport.

### Best Scaffold Candidate: crystaldba/postgres-mcp

**crystaldba/postgres-mcp** is the strongest Python starting point:

- ✅ Python, async-first (psycopg3), read-only mode, arbitrary query execution
- ✅ Works with any PostgreSQL (including self-hosted VMs)
- ✅ Can run in Azure Container Apps
- ❌ **Requires:** column whitelisting layer, parameterized template registry, ChatGPT OAuth/Streamable HTTP transport bridging

### Secondary Scaffold: pgEdge (if confidence in non-Python feasibility)

**pgEdge** is production-ready but:

- ✅ Mature, GA (April 2026), HTTP support, arbitrary queries, self-hosted PostgreSQL
- ⚠️ Language unknown (not confirmed Python)
- ❌ No column whitelisting, no OAuth 2.1

### PostgreSQL Security Model Limitation

All servers delegate column-level access control to PostgreSQL's native GRANT/REVOKE mechanism. **However, research shows that none redact regulated columns from query results at the MCP layer.** Even if you configure PostgreSQL column-level permissions, the LLM will still see plaintext PII in result rows if the query succeeds. You must implement **your own redaction/whitelisting layer** before rows reach the LLM.

### Transport: Streamable HTTP + OAuth 2.1 is Emerging

The MCP specification added Streamable HTTP and OAuth 2.1 support in March 2025 (alongside OpenAI's ChatGPT MCP support). Few servers have adopted this yet. Consider the `postgresql-ssh-mcp` project as a reference for modern transport patterns.

---

## Recommendation Summary

### **BUILD, not ADOPT.**

**Rationale:**

1. **Column-level whitelisting is mandatory and universally absent.** No evaluated server provides it; building custom ensures this non-negotiable requirement is met from day one.

2. **crystaldba/postgres-mcp is an excellent Python scaffold**, but you will need to:
   - Add a schema whitelisting/filtering layer (column blacklist or whitelist configuration)
   - Implement a parameterized query template registry
   - Bridge Streamable HTTP + OAuth 2.1 transport for ChatGPT Enterprise (or use a reverse proxy)

3. **pgEdge is an alternative if language flexibility exists**, but language confirmation is needed, and it has the same whitelisting/template gaps.

4. **No turnkey option saves development time** if the 7 requirements are firm. Adopting a server missing whitelisting and then adding it as a custom layer defeats the purpose.

### Implementation Path

**Option A (Recommended):**
- **Fork or extend `crystaldba/postgres-mcp`** as your base.
- Add column whitelisting via a YAML/JSON config layer.
- Build a parameterized template registry (in-memory or database-backed).
- Implement Streamable HTTP + OAuth 2.1 transport via a wrapper or direct MCP SDK integration.
- Deploy to Azure Container Apps.

**Option B (If pgEdge language is confirmed as Python):**
- Evaluate pgEdge's extensibility.
- Add column whitelisting and template support.
- Upgrade transport to OAuth 2.1 / Streamable HTTP.

**Option C (Greenfield):**
- Build from the MCP Python SDK directly, using AWS Labs' read-only keyword blocklist as a reference pattern for safety.
- Guarantee column whitelisting from the start.

---

## Sources

- [Azure Database for PostgreSQL Tools — Azure MCP Server (learn.microsoft.com)](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/azure-database-postgresql)
- [Azure/azure-mcp (github.com)](https://github.com/Azure/azure-mcp)
- [crystaldba/postgres-mcp (github.com)](https://github.com/crystaldba/postgres-mcp)
- [pgEdge Postgres MCP Server Blog (pgedge.com, April 2026)](https://www.pgedge.com/blog/introducing-the-pgedge-postgres-mcp-server)
- [pgEdge Documentation — MCP Protocol (docs.pgedge.com)](https://docs.pgedge.com/pgedge-postgres-mcp-server/development/developers/mcp-protocol/)
- [AWS Labs postgres-mcp-server (awslabs.github.io/mcp)](https://awslabs.github.io/mcp/servers/postgres-mcp-server)
- [modelcontextprotocol/servers-archived (github.com)](https://github.com/modelcontextprotocol/servers-archived)
- [MCP and Connectors — OpenAI API (developers.openai.com)](https://developers.openai.com/api/docs/guides/tools-connectors-mcp)
- [PostgreSQL MCP Server — Secure Setup for Claude & AI Agents (strac.io, 2026)](https://www.strac.io/blog/postgres-mcp-server)
- [MCP vulnerability case study: SQL injection in the Postgres MCP server (Datadog Security Labs)](https://securitylabs.datadoghq.com/articles/mcp-vulnerability-case-study-SQL-injection-in-the-postgresql-mcp-server/)
- [Supercharging AWS database development with AWS MCP servers (aws.amazon.com/blogs)](https://aws.amazon.com/blogs/database/supercharging-aws-database-development-with-aws-mcp-servers/)
- [Deep-wiki: Azure/azure-mcp (2026-06-18)](https://deepwiki.com)
- [Deep-wiki: modelcontextprotocol/servers (2026-06-18)](https://deepwiki.com)
