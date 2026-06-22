# Azure VM Test Deploy Runbook — pg-mcp-server (synthetic data, no-auth)

Stand up `pg-mcp-server` from scratch on a Several Millers Azure VM for **functionality
testing only**, using the synthetic fixture (`sql/synthetic_load.sql`) and no authentication.
This is the execution guide for **spec 003**.

> ⚠️ **Security ground rule.** No-auth means the `/mcp/` endpoint must **never** be reachable
> from the internet. The VM opens **only SSH (22)** inbound — never 5432 or 8000. The server
> binds to `127.0.0.1` and you reach it through an **SSH tunnel**. If you ever need a publicly
> reachable endpoint, stop and switch to the spec 002 OAuth path instead.

Commands are tagged **[LAPTOP]** (run on your Windows machine, PowerShell) or **[VM]** (run on
the Ubuntu VM over SSH).

---

## 0. Names used throughout (adjust to taste)

| Placeholder | Value used here | Notes |
|-------------|-----------------|-------|
| Resource group | `rg-sm-pgmcp-test` | New, so teardown is one click |
| Region | *closest to you* (e.g. `East US`) | Match existing SM resources if relevant |
| VM name | `vm-pgmcp-test` | |
| Image | **Ubuntu Server 24.04 LTS** | Ships modern glibc; `uv` provides Python 3.12 |
| Size | **Standard_B2s** (2 vCPU / 4 GB) | Cheap; enough for a test. B1s also works |
| Admin user | `azureuser` | |
| DB name | `mg_dwh` | |
| Schema | `centric_8_plm` | Created by the fixture |
| Read-only role | `mcp_readonly` | From `scripts/generate_role_sql.py` |
| Your laptop IP | `<YOUR_IP>` | For locking the SSH rule down |

Find `<YOUR_IP>` with: **[LAPTOP]** `curl https://ifconfig.me`

---

## 1. Create the VM (Azure Portal)

1. **Resource group** — Portal → *Resource groups* → **Create** → name `rg-sm-pgmcp-test`, pick your region → **Review + create**.
2. **Virtual machine** — Portal → *Virtual machines* → **Create → Azure virtual machine**:
   - *Basics*: RG `rg-sm-pgmcp-test`, VM name `vm-pgmcp-test`, region as above, Image **Ubuntu Server 24.04 LTS - x64 Gen2**, Size **Standard_B2s**.
   - *Administrator account*: **SSH public key**, username `azureuser`. Either let Azure generate a key pair (download the `.pem`) or paste your own public key.
   - *Inbound port rules*: **Allow selected ports → SSH (22) only**. **Do not** add 5432 or 8000.
3. **Review + create → Create.** If Azure generated the key, **download the private key now** (you can't later).
4. When deployment finishes → **Go to resource** → copy the **Public IP address**.
5. *(Recommended)* **Networking → the NSG rule for port 22 → Source = IP Addresses → `<YOUR_IP>/32`.** Restricts SSH to just you.
6. *(Recommended, cost)* VM → **Auto-shutdown** → enable a daily shutdown time.

**Verify:** the VM shows **Running** with a public IP.

---

## 2. Connect over SSH

**[LAPTOP]**
```powershell
# If Azure gave you a .pem, lock its permissions first (PowerShell):
icacls "$HOME\Downloads\vm-pgmcp-test_key.pem" /inheritance:r /grant:r "$($env:USERNAME):(R)"

ssh -i "$HOME\Downloads\vm-pgmcp-test_key.pem" azureuser@<PUBLIC_IP>
```

**Verify:** you land at an `azureuser@vm-pgmcp-test:~$` prompt.

---

## 3. Install PostgreSQL + create the database

**[VM]**
```bash
sudo apt-get update && sudo apt-get install -y postgresql
sudo systemctl enable --now postgresql
sudo -u postgres createdb mg_dwh
```

**Verify:** `sudo -u postgres psql -d mg_dwh -c '\conninfo'` connects.

> Native `apt` Postgres listens on `localhost:5432` and Ubuntu's `pg_hba.conf` allows
> password (`scram-sha-256`) logins over `127.0.0.1` — exactly what the server needs. No
> Postgres config changes required.

---

## 4. Load the synthetic data

The fixture is `pg-mcp-server/sql/synthetic_load.sql` — **synthetic only, safe to copy**.

**[LAPTOP]**
```powershell
scp -i "$HOME\Downloads\vm-pgmcp-test_key.pem" `
  "C:\Users\Praveen\Downloads\projects\thoughtfully\custom-mcp-plm-sm\pg-mcp-server\sql\synthetic_load.sql" `
  azureuser@<PUBLIC_IP>:/tmp/
```

**[VM]**
```bash
sudo -u postgres psql -d mg_dwh -v ON_ERROR_STOP=1 -f /tmp/synthetic_load.sql
```

**Verify:**
```bash
sudo -u postgres psql -d mg_dwh -c "SELECT count(*) FROM centric_8_plm.styles;"   # expect 200
```

---

## 5. Get the server code onto the VM

**Option A — git clone (preferred, if the repo is on a remote the VM can reach):**

**[VM]**
```bash
sudo apt-get install -y git
git clone <your-repo-url> sm-mcp && cd sm-mcp/pg-mcp-server
```

**Option B — clean copy from your laptop (no remote needed).** `git archive` ships only
tracked files (no `.venv`, no `.env`):

**[LAPTOP]**
```powershell
cd "C:\Users\Praveen\Downloads\projects\thoughtfully\custom-mcp-plm-sm"
git archive --format=tar.gz --prefix=pg-mcp-server/ -o "$env:TEMP\pgmcp.tgz" HEAD:pg-mcp-server
scp -i "$HOME\Downloads\vm-pgmcp-test_key.pem" "$env:TEMP\pgmcp.tgz" azureuser@<PUBLIC_IP>:/tmp/
```
**[VM]**
```bash
mkdir -p ~/sm-mcp && tar -xzf /tmp/pgmcp.tgz -C ~/sm-mcp && cd ~/sm-mcp/pg-mcp-server
```

**Verify:** `ls` shows `main.py`, `policy.yaml`, `scripts/`, `sql/`.

---

## 6. Create the column-scoped read-only role

Regenerate the role SQL from the policy, set a real password, and apply it.

**[VM]** (from `pg-mcp-server/`, after installing `uv` in step 7 — or just edit the committed `sql/role_setup.sql`)
```bash
# pick a strong password and substitute it for CHANGE_ME:
sed -i "s/CHANGE_ME/$(openssl rand -base64 18)/" sql/role_setup.sql
grep "CREATE ROLE" sql/role_setup.sql        # copy the password — you need it in step 8
sudo -u postgres psql -d mg_dwh -v ON_ERROR_STOP=1 -f sql/role_setup.sql
```

**Verify** the role can read but not write:
```bash
psql -h 127.0.0.1 -U mcp_readonly -d mg_dwh -c "SELECT code FROM centric_8_plm.styles LIMIT 1;"
psql -h 127.0.0.1 -U mcp_readonly -d mg_dwh -c "INSERT INTO centric_8_plm.styles(id) VALUES ('x');"
# the INSERT must fail with: cannot execute INSERT in a read-only transaction
```

---

## 7. Install `uv` and sync dependencies

**[VM]**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
cd ~/sm-mcp/pg-mcp-server      # (or ~/sm-mcp/.../pg-mcp-server if you cloned)
uv sync                        # uv fetches Python 3.12 and installs deps
```

**Verify:** `uv run python --version` prints 3.12.x.

---

## 8. Configure `.env` (no-auth, localhost)

**[VM]** create `pg-mcp-server/.env`:
```bash
cat > .env <<EOF
PGMCP_DATABASE_URL=postgresql://mcp_readonly:<PASSWORD_FROM_STEP_6>@127.0.0.1:5432/mg_dwh
PGMCP_HOST=127.0.0.1
PGMCP_OAUTH_ISSUER_URL=
PGMCP_OAUTH_JWKS_URI=
PGMCP_OAUTH_AUDIENCE=
EOF
```
> Leave the three `PGMCP_OAUTH_*` blank → no-auth. `PGMCP_HOST=127.0.0.1` keeps it off every
> public interface. No `?sslmode=require` here — it's a local loopback connection.

**Verify:** `uv run python -c "from config import get_settings; get_settings()"` exits with no error.

---

## 9. Run the server

**[VM]** — foreground first, to read the startup log:
```bash
uv run python main.py
```
**Verify** the log shows, in order:
```
OAuth not configured — running WITHOUT authentication (local dev only)
database pool opened
policy validated against DB: 5 tables, 2 templates
Uvicorn running on http://127.0.0.1:8000
```
Leave it running, or run it detached:
```bash
nohup uv run python main.py > server.log 2>&1 &
```

---

## 10. Smoke-test end to end

**[VM]** (a second SSH session, or after backgrounding step 9):
```bash
cd ~/sm-mcp/pg-mcp-server
uv run python scripts/smoke_test.py --url http://127.0.0.1:8000/mcp/
```
**Verify:** prints `9/9 checks passed` and exits 0 (tools listed; `styles` advertised; hidden
column absent; open query + both templates return rows; non-whitelisted column, `SELECT *`,
and a write are each rejected before the DB).

---

## 11. Reach it from your laptop (SSH tunnel)

To drive the server from an MCP inspector or `smoke_test.py` on your machine, forward the port
over SSH — the endpoint stays bound to the VM's loopback:

**[LAPTOP]**
```powershell
ssh -i "$HOME\Downloads\vm-pgmcp-test_key.pem" -L 8000:127.0.0.1:8000 azureuser@<PUBLIC_IP>
# leave this open; in another terminal point the client at:
#   http://127.0.0.1:8000/mcp/
```

---

## 12. Teardown (when testing is done)

- **Pause (keep state, stop billing compute):** VM → **Stop** (Deallocate).
- **Delete everything:** *Resource groups* → `rg-sm-pgmcp-test` → **Delete resource group**.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `psql: peer authentication failed` for `mcp_readonly` | You used the Unix socket. Add `-h 127.0.0.1` to force TCP + password auth. |
| Role connects but `SELECT` is denied | Re-run `scripts/generate_role_sql.py` after any `policy.yaml` change, re-apply `sql/role_setup.sql`. |
| Server log says `OAuth enabled` | A `PGMCP_OAUTH_*` var is set. Blank all three for the no-auth test. |
| `smoke_test.py` can't connect | Server not up, or wrong URL. Confirm step 9's log and the trailing slash in `/mcp/`. |
| Tunnel open but client refused | Server bound to `0.0.0.0`/wrong port, or `PGMCP_HOST` not `127.0.0.1`. The tunnel forwards to `127.0.0.1:8000` on the VM. |
| `uv: command not found` after install | `source $HOME/.local/bin/env` (or open a new shell). |

> Spec: `specs/003-several-millers-test-deploy.md`. Depends on spec 001 (`policy.yaml`,
> `main.py`, `config.py`, `scripts/generate_role_sql.py`). This is the interim stand-in for
> the spec 002 production OAuth deploy.
