# Azure Container Apps Deployment — Reference Summary

**Source:** Microsoft Learn official documentation
**Retrieved:** 2026-06-18
**Version:** Azure Container Apps (default Workload Profiles environment)

## Overview

Deployment of containerized Python MCP servers to Azure Container Apps with VNet integration (private Postgres access) and external HTTPS ingress. This covers the specific scenario: public ingress on port 8000, private VNet connectivity to self-hosted PostgreSQL on port 5432, and secrets management via Azure Key Vault with RBAC.

## 1. Azure Container Registry (ACR) Setup

### Create Registry
- **Portal location:** Azure Portal → Search "Container Registry" → Create → Basic SKU
- **Key settings:**
  - Admin user: Optional (not required if using managed identity authentication)
  - ARM tokens for authentication: Must be enabled for managed identity image pull

### Server-Side Build (No Local Docker)
```bash
az acr build -r <acr-name> -t pg-mcp-server:latest .
```
- Builds the image directly in ACR (no local Docker daemon required)
- Automatically pushes to the registry

### Image Authentication: Managed Identity vs. Admin User

**Managed Identity (Preferred)**
- Container Apps pulls images via system-assigned or user-assigned managed identity
- App needs `acrpull` role on the ACR resource
- No credentials stored in Container Apps configuration
- Automatic token refresh

**Admin User (Legacy)**
- Admin credentials stored as secrets in Container Apps
- Less secure; only use if managed identity not available

---

## 2. Virtual Network Configuration

### Subnet Requirements (Workload Profiles Environment)

**Minimum subnet size:** `/27` CIDR block
- For legacy Consumption-only environment: `/23` (larger; not used here)
- Workload Profiles is the default and recommended type

**Delegation String**
```
Microsoft.App/environments
```
Subnet must be delegated exclusively to Container Apps; no other services can use it.

### Portal Steps
1. **Create VNet:** Azure Portal → Virtual Networks → Create
   - Address space (e.g., `10.0.0.0/16`)
2. **Create Subnet:**
   - Name: (e.g., `container-apps-subnet`)
   - Address range: `/27` or larger (e.g., `10.0.0.0/27` gives 32 addresses)
   - **Delegate to:** `Microsoft.App/environments`
3. **Create separate subnet for Postgres VM**
   - E.g., `10.0.1.0/24` (not delegated)

### CLI Alternative
```bash
az network vnet subnet update \
  --resource-group <rg> \
  --vnet-name <vnet> \
  --name <subnet> \
  --delegations Microsoft.App/environments
```

---

## 3. Network Security Group (NSG) Rules

### Inbound Rule for Postgres VM Access

**Scenario:** Container Apps subnet → Postgres VM (self-hosted) on TCP port 5432

| Setting | Value |
|---------|-------|
| **Protocol** | TCP |
| **Destination Port** | 5432 |
| **Destination IP/CIDR** | Postgres VM private IP or subnet CIDR |
| **Source IP/CIDR** | Container Apps subnet (e.g., `10.0.0.0/27`) |
| **Action** | Allow |
| **Priority** | 100 (or next available) |

### Portal Steps
1. NSG → Inbound security rules → Add
2. Protocol: TCP
3. Destination port ranges: `5432`
4. Source: IP Addresses / `<container-apps-subnet-cidr>`
5. Action: Allow
6. Attach NSG to Postgres VM's network interface or subnet

---

## 4. Container Apps Environment

### Environment Type & VNet Integration

**Type:** Workload Profiles (default)
- Supports UDRs, Azure NAT Gateway, private endpoints
- Minimum subnet size `/27`

### Portal Setup Steps

1. **Create Environment:**
   - Azure Portal → Container Apps → Create new app (or create environment separately)
   - Environment name: (e.g., `pg-mcp-env`)
   - Region: (e.g., `East US`)

2. **Networking Tab:**
   - **Use your own virtual network:** Yes
   - **Virtual network:** Select the VNet created above
   - **Subnet:** Select the delegated Container Apps subnet
   - **Virtual IP:** External (to allow public ingress)
   - **Public network access:** Enabled

3. **Monitoring Tab:**
   - **Log Analytics workspace:** Create or select existing
   - Required for diagnostics and logging

### CLI Alternative
```bash
az containerapp env create \
  --name <env-name> \
  --resource-group <rg> \
  --location <location> \
  --infrastructure-subnet-resource-id <subnet-id>
```

---

## 5. Azure Key Vault with RBAC

### Why Contributor Role Doesn't Grant Secret Access

With **Azure RBAC permission model** (not the legacy access policies):
- **Contributor** role = control plane access only (create, delete, manage Key Vault resources)
- **Secret access** = data plane operation; requires separate data plane role

### Required Roles

| Role | Purpose | Who |
|------|---------|-----|
| **Key Vault Secrets Officer** | Create/read/write/delete secrets | Human operator (you) |
| **Key Vault Secrets User** | Read secret values at runtime | App's managed identity |

### Setup Steps

1. **Create Key Vault:**
   - Azure Portal → Key Vault → Create
   - **Permission model:** Azure role-based access control (RBAC)
   - Leave vault access policies disabled (RBAC is enabled)

2. **Assign Role to Your User (Portal):**
   - Key Vault → Access Control (IAM) → Add Role Assignment
   - Role: **Key Vault Secrets Officer**
   - Assign to: Your user account
   - This allows you to create/manage secrets

3. **Create Secrets:**
   - Key Vault → Secrets → Generate/Import
   - E.g., secret name: `database-url`
   - Value: Full PostgreSQL connection string (e.g., `postgresql://user:pass@vm-ip:5432/dbname`)

4. **Get Secret URI:**
   - Open secret → Copy **Secret Identifier**
   - Format: `https://<vault-name>.vault.azure.net/secrets/<secret-name>/<version-id>`
   - Used in Container Apps secret reference

5. **Assign Role to App's Managed Identity (Portal or CLI):**
   - Key Vault → Access Control (IAM) → Add Role Assignment
   - Role: **Key Vault Secrets User**
   - Assign to: The Container App's managed identity (system-assigned or user-assigned)
   - Scope: Key Vault resource

---

## 6. Container App Configuration

### Managed Identity

**Portal Steps:**
1. Container App → Identity (left menu, under Settings)
2. System assigned tab → Status: **On** → Save
3. Confirm enrollment with Microsoft Entra ID

**Identity is required for:**
- Reading secrets from Key Vault at runtime
- Pulling images from ACR (if using managed identity auth)

### Ingress Configuration

| Setting | Value |
|---------|-------|
| **Ingress enabled** | Yes |
| **Ingress type** | HTTP |
| **External** | Yes (public internet access) |
| **Target port** | 8000 |
| **Accept traffic from anywhere** | Yes (or configure IP restrictions if needed) |

**Portal Steps:**
1. Container App → Ingress (left menu, under Settings)
2. Enable ingress: On
3. Ingress type: HTTP
4. External: On
5. Target port: 8000 (where your HTTPS server listens)
6. Traffic: Accept from anywhere

### Secrets & Environment Variables

**Defining Secrets (Portal):**
1. Container App → Secrets (under Security)
2. Add → Type: **Key Vault reference**
3. Name: `database-url`
4. Key Vault secret URL: (paste the Secret Identifier from Key Vault)
5. Identity: **System assigned**
6. Add

**Referencing in Environment Variables (Portal):**
1. Container App → Revisions and replicas
2. Create new revision → Edit container
3. Environment variables tab → Add
4. Name: `DATABASE_URL` (or your app's env var name)
5. Source: **Reference a secret**
6. Value: Select `database-url` (the secret name created above)
7. Save → Create revision

---

## 7. Key Vault Reference Syntax

For CLI deployments (when using `--secrets` parameter):

**System-Assigned Identity:**
```
--secrets database-url=keyvaultref:<secret-uri>,identityref:system
```

**User-Assigned Identity:**
```
--secrets database-url=keyvaultref:<secret-uri>,identityref:<identity-resource-id>
```

Example:
```bash
az containerapp create \
  --name pg-mcp-server \
  --resource-group <rg> \
  --environment <env-name> \
  --image <acr>.azurecr.io/pg-mcp-server:latest \
  --system-assigned \
  --target-port 8000 \
  --ingress external \
  --secrets database-url=keyvaultref:https://myvault.vault.azure.net/secrets/database-url/abc123,identityref:system
```

---

## 8. Finding the Application URL

**Public Ingress Endpoint:**
1. Container App → Overview (top section)
2. **Application Url:** (e.g., `https://pg-mcp-server.abc123.eastus.azurecontainerapps.io`)
3. Your MCP endpoint: `https://pg-mcp-server.abc123.eastus.azurecontainerapps.io/mcp/`

The FQDN is auto-generated and reachable from the public internet when external ingress is enabled.

---

## 9. Common Gotchas & Troubleshooting

### Subnet Delegation Issues
- If you create a Container Apps environment without delegating the subnet, you'll get deployment errors
- Fix: Delete environment, delegate subnet to `Microsoft.App/environments`, recreate

### Key Vault Authentication Failures
- **Error:** "Managed identity not enabled"
  - Fix: Enable system-assigned identity on Container App (Identity → System assigned → On)
- **Error:** "RBAC permission denied"
  - Fix: Ensure managed identity has **Key Vault Secrets User** role on Key Vault (not just Contributor)
- **Error:** "Secret disabled in Key Vault"
  - Fix: Key Vault → Secrets → Open secret → Enabled: Yes

### ACR Image Pull Failures
- If using managed identity, ensure container app has `acrpull` role on ACR
- Check: ACR → Access Control (IAM) → Verify managed identity is listed with acrpull role
- Alternative: Use admin credentials if managed identity not available (less secure)

### VNet Isolation / Postgres Connectivity
- Container Apps can only reach Postgres if:
  1. NSG allows inbound on Postgres VM from Container Apps subnet
  2. Postgres VM is in same VNet or peered VNet
  3. Routing/firewall rules allow egress from Container Apps subnet
- Test with a simple `curl` or network test container if connectivity fails

---

## 10. Deploy Flow (Portal-First Approach)

1. **Create VNet & Subnets** (delegated for Container Apps)
2. **Create/Configure ACR** (Basic SKU, ARM tokens enabled)
3. **Create Key Vault** (RBAC permission model)
4. **Create Secrets in Key Vault** (database connection string)
5. **Assign Key Vault Secrets Officer role** to your user (to manage secrets)
6. **Create Container Apps Environment** (VNet-integrated, Workload Profiles)
7. **Create Container App:**
   - Enable system-assigned managed identity
   - Configure ingress (HTTP, external, port 8000)
   - Define secrets (Key Vault references)
   - Set environment variables (reference secrets)
   - Deploy container image from ACR
8. **Assign Key Vault Secrets User role** to app's managed identity (for runtime access)
9. **Test:** Call `https://<app-url>/mcp/` from outside; verify Postgres connectivity logs

---

## References

- [Integrate a virtual network with Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom)
- [Networking in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/networking)
- [Manage secrets in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- [Managed identities in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- [Managed identity image pull from ACR](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull)
- [Ingress in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- [Azure Key Vault RBAC guide](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide)
- [Azure Container Registry concepts](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-concepts)
