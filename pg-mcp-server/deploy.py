"""Deploy skeleton for Azure Container Apps (VNet-integrated) + Azure Key Vault.

SKELETON (decision D4). It builds the image in ACR and creates/updates a VNet-integrated
Container App whose database connection string comes from Key Vault. The Container Apps
environment must already be VNet-integrated into the Postgres VM's VNet, with an NSG rule
allowing the app subnet to reach the VM on 5432. Detailed production hardening (autoscale,
managed-identity RBAC, private DNS) is deferred to a follow-on deploy spec.

Fill in resource names via env vars, then:
    uv run python deploy.py           # dry-run: print the az commands
    uv run python deploy.py --apply   # run them (requires `az login`)
"""

import os
import subprocess
import sys

RESOURCE_GROUP = os.environ.get("AZ_RESOURCE_GROUP", "<resource-group>")
ACR = os.environ.get("AZ_ACR", "<acr-name>")  # Azure Container Registry
APP = os.environ.get("AZ_APP", "pg-mcp-server")
ENVIRONMENT = os.environ.get("AZ_CONTAINERAPPS_ENV", "<vnet-integrated-env>")
KEY_VAULT = os.environ.get("AZ_KEY_VAULT", "<key-vault-name>")
DB_SECRET = os.environ.get("AZ_DB_SECRET", "pgmcp-database-url")  # Key Vault secret name
IMAGE = f"{ACR}.azurecr.io/{APP}:latest"


def steps() -> list[list[str]]:
    return [
        # Build + push the image directly in ACR (no local Docker needed).
        ["az", "acr", "build", "--registry", ACR, "--image", f"{APP}:latest", "."],
        # Create/update the Container App with public HTTPS ingress and a Key Vault secret.
        [
            "az",
            "containerapp",
            "create",
            "--name",
            APP,
            "--resource-group",
            RESOURCE_GROUP,
            "--environment",
            ENVIRONMENT,
            "--image",
            IMAGE,
            "--target-port",
            "8000",
            "--ingress",
            "external",  # public HTTPS; ChatGPT connector URL = https://<fqdn>/mcp/
            "--system-assigned",  # managed identity used to read Key Vault
            "--secrets",
            f"database-url=keyvaultref:{KEY_VAULT}/{DB_SECRET},identityref:system",
            "--env-vars",
            "PGMCP_DATABASE_URL=secretref:database-url",
        ],
    ]


def main(apply: bool) -> None:
    for command in steps():
        print(" ".join(command))
        if apply:
            subprocess.run(command, check=True)  # noqa: S603 (fixed, non-user input)


if __name__ == "__main__":
    main(apply="--apply" in sys.argv[1:])
