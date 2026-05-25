# Troubleshooting Log — LLMOps Platform on Azure

Real issues encountered during Phase 1 and Phase 2 deployment, with root causes, fixes applied, and lessons learned.

---

## Phase 1 — Infrastructure

---

### Issue 1: Duplicate Provider Block in Terraform

**Error**
```
Error: Duplicate provider configuration
on main.tf line 36: provider "azurerm" {
A default (non-aliased) provider configuration for "azurerm" was already given at main.tf:23
```

**Root Cause**
`cat >>` appended a second `provider "azurerm"` block to `main.tf` instead of replacing the existing one.

**Fix**
Rewrote `main.tf` cleanly using `cat >` (overwrite) instead of `cat >>` (append).

**Lesson**
Always use `cat >` for full file rewrites. Use `cat >>` only for intentional appends.
When editing Terraform files, prefer Python `str.replace()` for targeted edits over shell appends.

---

### Issue 2: AKS Kubernetes Version Not Supported (LTS-only)

**Error**
```
K8sVersionNotSupported: Managed cluster aks-llmops-prod is on version 1.29/1.30/1.31
which is only available for Long-Term Support (LTS).
```

**Root Cause**
Free tier Azure subscriptions only support LTS versions of Kubernetes (1.30, 1.31, 1.32+).
Pinning to a specific version without checking regional support caused repeated failures.

**Fix**
Removed the `kubernetes_version` pin entirely — AKS auto-selects the latest supported version.
Cluster deployed on `v1.34.7`.

**Lesson**
Never hardcode Kubernetes versions without first running `az aks get-versions --location <region> --output table`.
On free tier subscriptions, let AKS choose the default version.

---

### Issue 3: Key Vault — SubnetsHaveNoServiceEndpointsConfigured

**Error**
```
VirtualNetworkNotValid: Subnets snet-aks do not have ServiceEndpoints
for Microsoft.KeyVault resources configured.
```

**Root Cause**
Key Vault network ACL referenced the AKS subnet but the subnet had no `Microsoft.KeyVault` service endpoint configured.

**Fix**
Added `service_endpoints = ["Microsoft.KeyVault", "Microsoft.Storage"]` to the AKS subnet in `networking/main.tf`.

**Lesson**
When restricting Key Vault or Storage to a specific subnet via network ACLs, the subnet must have the corresponding service endpoint enabled. Service endpoints and private endpoints are different — service endpoints allow subnet-level access without a private IP.

---

### Issue 4: PostgreSQL — ConflictingPublicNetworkAccessAndVirtualNetworkConfiguration

**Error**
```
ConflictingPublicNetworkAccessAndVirtualNetworkConfiguration:
Public Network Access is not supported along with Virtual Network feature.
```

**Root Cause**
PostgreSQL Flexible Server cannot have both VNet integration (`delegated_subnet_id`) and `public_network_access_enabled = true` simultaneously.

**Fix**
Set `public_network_access_enabled = false` explicitly in the PostgreSQL module.

**Lesson**
Azure PostgreSQL Flexible Server has two mutually exclusive networking modes: public access with firewall rules OR private VNet integration. Choose one at creation time — switching requires recreation.

---

### Issue 5: PostgreSQL — LocationIsOfferRestricted (eastus)

**Error**
```
LocationIsOfferRestricted: Subscriptions are restricted from provisioning
in location 'eastus'. Try again in a different location.
```

**Root Cause**
Free tier Azure subscriptions cannot provision PostgreSQL Flexible Server in `eastus`.

**Fix**
Moved PostgreSQL to `canadacentral` by introducing a `postgresql_location` variable.
Also removed VNet integration (delegated subnet) since VNet was in `eastus` and PostgreSQL moved to `canadacentral` — cross-region VNet integration is not supported.

**Lesson**
Free tier subscriptions have regional restrictions on specific services. Always test service availability with a quick `az postgres flexible-server create` dry run before committing to a region in Terraform.

---

### Issue 6: PostgreSQL — Missing Subnet Delegation

**Error**
```
OperationFailed: The subnet name as snet-private-endpoints is missing
required delegations Microsoft.DBforPostgreSQL/flexibleServers
```

**Root Cause**
PostgreSQL Flexible Server with VNet integration requires a dedicated subnet with `Microsoft.DBforPostgreSQL/flexibleServers` delegation. It cannot share the private endpoints subnet.

**Fix**
Added a new `azurerm_subnet.postgresql` resource with the required delegation block in `networking/main.tf`.

**Lesson**
PostgreSQL Flexible Server subnet delegation is exclusive — no other resources can use the same subnet. Always create a dedicated subnet for PostgreSQL VNet integration.

---

### Issue 7: Storage Containers — 403 AuthorizationFailure

**Error**
```
checking for existing Container "raw-documents": unexpected status 403
AuthorizationFailure: This request is not authorized to perform this operation.
```

**Root Cause**
Storage account had `public_network_access_enabled = false`. Terraform running from a laptop couldn't create containers because the local machine IP was not whitelisted before the network rules applied.

**Fix**
- Set `public_network_access_enabled = true` during bootstrap phase
- Added `TF_VAR_allowed_ip` with current machine IP to storage network rules
- Added `depends_on = [azurerm_storage_account_network_rules.main]` to all container resources

**Lesson**
This is the classic bootstrap chicken-and-egg problem. The production pattern is to run Terraform from inside the private network (CI/CD agent in VNet). For bootstrap, temporarily allow public access with IP restriction, then harden post-deploy.

---

### Issue 8: AKS VM SKU Not Allowed (Free Tier Restriction)

**Error**
```
BadRequest: The VM size of Standard_B2s / Standard_D4s_v3 / Standard_DS3_v2
is not allowed in your subscription in location 'eastus'.
```

**Root Cause**
Free tier Azure subscriptions in eastus only allow DC/EC/FX/HB/M/NC series VMs for AKS. Standard D/B/F series are not permitted.

**Fix**
Changed all node pool VM sizes to `Standard_DC2s_v3` (confidential compute series).

**Lesson**
Always run `az aks get-versions --location <region>` and `az vm list-usage --location <region>` before designing node pool VM sizes. Document subscription-level VM family restrictions in your Architecture Decision Records (ADRs).

---

### Issue 9: vCPU Quota Exhaustion

**Error**
```
ErrCode_InsufficientVCPUQuota: Insufficient regional vcpu quota left for location eastus.
left regional vcpu quota 0, requested quota 4.
```

**Root Cause**
`Standard DCSv3 Family` quota was 4 vCPUs total. System pool (2× DC2s_v3 = 4 vCPUs) consumed entire quota. No vCPUs left for CPU node pool.

**Fix**
- Scaled system pool from 2 nodes to 1 node (freed 2 vCPUs)
- Deleted and recreated CPU node pool with `Standard_DC2s_v3` (2 vCPUs) instead of `Standard_DC4s_v3` (4 vCPUs)
- Set CPU node pool `min_count = 0`

**Lesson**
On free tier subscriptions, vCPU quota per VM family is very limited (typically 4 per family). Plan node pool VM sizes around available quota. Use `az vm list-usage --location <region> --output table` to check quotas before designing the cluster.

---

### Issue 10: Terraform tfvars Sensitive Variable Syntax

**Error**
```
Error: Invalid single-argument block definition
variable "postgresql_password" { type = string  sensitive = true }
A single-line block definition must end with a closing brace immediately after its single argument definition.
```

**Root Cause**
Terraform single-line variable blocks cannot have more than one argument. `type` and `sensitive` must be on separate lines.

**Fix**
```hcl
variable "postgresql_password" {
  type      = string
  sensitive = true
}
```

**Lesson**
Terraform single-line block syntax `{ key = value }` only supports one argument. Multi-attribute variables must use multi-line syntax.

---

### Issue 11: Terraform Backend — SubscriptionNotFound

**Error**
```
SubscriptionNotFound: Subscription e56f284c was not found.
```

**Root Cause**
Azure CLI session was authenticated to a work account (WGACA) but the subscription ID referenced a personal account. The `Microsoft.Storage` resource provider was also not registered on the new personal subscription.

**Fix**
- Logged out and re-authenticated with personal Microsoft account using `az login --use-device-code`
- Registered all required resource providers via bootstrap script

**Lesson**
Always verify active subscription with `az account show` before running any Azure CLI commands. On new subscriptions, resource providers must be registered before creating resources of that type.

---

## Phase 2 — Data Ingestion Pipeline

---

### Issue 12: Airflow Helm — ServiceAccount Ownership Conflict

**Error**
```
ServiceAccount "ingestion-sa" in namespace "llmops" exists and cannot be imported
into the current release: invalid ownership metadata; label validation error:
missing key "app.kubernetes.io/managed-by": must be set to "Helm"
```

**Root Cause**
ServiceAccount was created manually with `kubectl create serviceaccount` before Helm install. Helm requires ownership labels/annotations on resources it manages.

**Fix**
Deleted the manually created ServiceAccount and let Helm recreate it with proper ownership metadata. Re-annotated with workload identity client ID after Helm deploy.

**Lesson**
Never manually create Kubernetes resources that Helm will also try to manage. Either manage the resource entirely outside Helm (with `helm.sh/resource-policy: keep` annotation) or let Helm own it from the start.

---

### Issue 13: Airflow Init Container Stuck — Missing DB Migration

**Symptom**
All Airflow pods stuck in `Init:0/1` for hours. Init container running `airflow db check-migrations` never completing.

**Root Cause**
Airflow's init container waits for database migrations to be applied before starting. Migrations had never been run — the `airflow` database existed but had no schema.

**Fix**
Ran `airflow db migrate` as a one-off Kubernetes pod:
```bash
kubectl run airflow-db-init --image=apache/airflow:2.8.3 --restart=Never \
  --namespace=llmops --overrides='{"spec":{"containers":[{"name":"airflow-db-init",
  "image":"apache/airflow:2.8.3","command":["airflow","db","migrate"],
  "env":[{"name":"AIRFLOW__DATABASE__SQL_ALCHEMY_CONN","valueFrom":
  {"secretKeyRef":{"name":"airflow-db-secret","key":"connection"}}}]}]}}'
```

**Lesson**
Airflow Helm chart does not run `db migrate` automatically unless `migrateDatabaseJob.enabled: true` is set in values. Always check Helm chart defaults for database migration behavior.

---

### Issue 14: kubectl logs — 504 Gateway Timeout (Kubelet Port 10250)

**Error**
```
error copying from remote stream to local connection:
proxy error from localhost:9443 while dialing 10.1.0.33:10250, code 504: 504 Gateway Timeout
```

**Root Cause**
NSG on the AKS subnet had a `deny-all-inbound` rule at priority 4096. This blocked the kubelet API on port 10250, which `kubectl logs`, `kubectl exec`, and `kubectl port-forward` rely on.

**Fix**
Added inbound NSG rule to allow port 10250 from VirtualNetwork:
```bash
az network nsg rule create --nsg-name nsg-aks-prod \
  --name allow-kubelet --priority 200 --direction Inbound \
  --protocol Tcp --destination-port-ranges 10250 \
  --source-address-prefixes VirtualNetwork --destination-address-prefixes VirtualNetwork
```

**Lesson**
AKS requires port 10250 (kubelet API) to be accessible within the VNet for `kubectl logs/exec` to work. Never add a blanket `deny-all-inbound` NSG rule without first adding the required AKS ports. Refer to Microsoft's AKS NSG requirements documentation before customizing network security.

---

### Issue 15: CoreDNS — External DNS Resolution Failure from Pods

**Error**
```
;; connection timed out; no servers could be reached
nslookup: can't resolve 'psql-llmops-prod.postgres.database.azure.com'
```

**Root Cause**
CoreDNS was configured to use `forward . /etc/resolv.conf`. The node's `/etc/resolv.conf` pointed to Azure's DNS server at `168.63.129.16`, but the custom NSG on the AKS subnet was blocking UDP/TCP port 53 outbound at the node NIC level (managed by the `MC_*` resource group NSG, not the subnet NSG).

**Fix**
Patched CoreDNS ConfigMap to forward directly to Azure DNS IP:
```bash
kubectl get configmap coredns -n kube-system -o json | \
  python3 -c "
import sys, json
cm = json.load(sys.stdin)
cm['data']['Corefile'] = cm['data']['Corefile'].replace(
    'forward . /etc/resolv.conf', 'forward . 168.63.129.16')
print(json.dumps(cm))" | kubectl apply -f -
kubectl rollout restart deployment coredns -n kube-system
```

**Lesson**
Azure's `168.63.129.16` is a platform-level DNS server that must always be reachable from AKS nodes. It also serves IMDS and health probe traffic. Never block outbound traffic to this IP in any NSG. Always include an explicit allow rule for `168.63.129.16` in AKS network designs.

---

### Issue 16: PostgreSQL Firewall — Private IPs Not Supported

**Symptom**
Added firewall rule `allow-aks` covering `10.1.0.0 - 10.1.255.255` (AKS pod subnet). Pods still got connection timeout on port 5432.

**Root Cause**
Azure PostgreSQL Flexible Server firewall rules do not support RFC1918 private IP ranges. Rules with private IPs are accepted by the API but never applied — the service only evaluates public IP firewall rules.

**Fix**
Added the special Azure convention firewall rule `0.0.0.0 - 0.0.0.0` which means "allow all Azure-internal services":
```bash
az postgres flexible-server firewall-rule create \
  --rule-name allow-azure-services \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

**Lesson**
PostgreSQL Flexible Server firewall rules only work for public IPs. For AKS pod access without VNet integration, use the `0.0.0.0/0.0.0.0` Azure services rule. For production with strict security, use VNet integration with subnet delegation instead.

---

### Issue 17: AKS-Managed NSG in MC_* Resource Group

**Symptom**
Custom NSG rules on `nsg-aks-prod` (in user resource group) had no effect on pod outbound traffic. Port 5432 still timed out even with explicit allow rules.

**Root Cause**
AKS creates and manages its own NSG (`aks-agentpool-XXXXXXXX-nsg`) in the automatically created `MC_*` node resource group. This NSG is attached to the node NICs and controls actual pod traffic. The subnet NSG in the user resource group applies to the subnet level but not the NIC level.

**Fix**
Added port 5432 outbound rule directly to the AKS-managed NSG:
```bash
az network nsg rule create \
  --resource-group MC_rg-llmops-prod_aks-llmops-prod_eastus \
  --nsg-name aks-agentpool-12381085-nsg \
  --name allow-postgres-outbound --priority 200 \
  --direction Outbound --protocol Tcp \
  --destination-port-ranges 5432
```

**Lesson**
AKS manages two NSGs: one on the subnet (user-controlled) and one on node NICs (AKS-managed in `MC_*` RG). Pod-level traffic is governed by the NIC NSG. Manual changes to the AKS-managed NSG may be overwritten during node pool upgrades — the production pattern is to use `--aad-admin-group-object-ids` and AKS network policies instead.

---

### Issue 18: Airflow Helm — Redis StatefulSet Deployed with KubernetesExecutor

**Symptom**
Helm install timed out waiting for `airflow-redis` StatefulSet even though KubernetesExecutor was configured (Redis is only needed for CeleryExecutor).

**Root Cause**
Default Helm values had Redis enabled. KubernetesExecutor doesn't use Redis but the chart still deployed it unless explicitly disabled.

**Fix**
Added `redis.enabled: false` and `workers.replicas: 0` to `values.yaml`.

**Lesson**
Always review Helm chart default values with `helm show values <chart>` before deploying. Many charts enable components by default that aren't needed for your executor/deployment pattern.

---

## Summary — Key Lessons

| # | Lesson |
|---|---|
| 1 | Check AKS supported versions per region before pinning: `az aks get-versions` |
| 2 | Check VM quota per family before designing node pools: `az vm list-usage` |
| 3 | Free tier subscriptions have VM family, region, and service restrictions — test early |
| 4 | Never block `168.63.129.16` — Azure DNS, IMDS, and health probes depend on it |
| 5 | PostgreSQL Flexible Server firewall rules don't support private RFC1918 IPs |
| 6 | AKS manages its own NSG in `MC_*` RG — subnet NSG alone is not enough |
| 7 | Terraform bootstrap is a chicken-and-egg problem — allow public access temporarily |
| 8 | Airflow db migrate must run before pods start — don't rely on Helm to do it automatically |
| 9 | CoreDNS `forward . /etc/resolv.conf` can fail if NSG blocks DNS — pin to `168.63.129.16` |
| 10 | Never manually create resources that Helm will manage — let Helm own them from the start |
| 11 | PostgreSQL + VNet integration requires dedicated subnet with delegation — no sharing |
| 12 | Use `cat >` for file rewrites, `cat >>` only for appends — prevent duplicate Terraform blocks |
| 13 | Always run `terraform validate` after every module change before `terraform plan` |
| 14 | Remote state backend must be bootstrapped manually before `terraform init` |
| 15 | `sensitive = true` in Terraform variables requires multi-line block syntax |

---

## Useful Diagnostic Commands

```bash
# Check AKS supported versions
az aks get-versions --location eastus --output table

# Check VM quota per family
az vm list-usage --location eastus --output table | grep -i standard

# List all NSG rules including defaults
az network nsg show --resource-group <rg> --name <nsg> --query "securityRules" --output table

# Check AKS-managed NSG
az network nsg list --resource-group MC_<rg>_<cluster>_<region> --output table

# Test DNS from pod
kubectl run dns-test --image=busybox --restart=Never --namespace=llmops \
  -- nslookup <hostname>
sleep 30 && kubectl logs dns-test -n llmops

# Test PostgreSQL from pod
kubectl run pg-test --image=postgres:16 --restart=Never --namespace=llmops \
  -- psql "postgresql://<user>@<host>/<db>?sslmode=require" -c "SELECT 1"
sleep 40 && kubectl logs pg-test -n llmops

# Check PostgreSQL firewall rules
az postgres flexible-server firewall-rule list \
  --resource-group <rg> --name <server> --output table

# Check CoreDNS config
kubectl get configmap coredns -n kube-system -o yaml

# Run Airflow db migrate manually
kubectl run airflow-db-init --image=apache/airflow:2.8.3 --restart=Never \
  --namespace=llmops --overrides='{"spec":{"containers":[{"name":"airflow-db-init",
  "image":"apache/airflow:2.8.3","command":["airflow","db","migrate"],
  "env":[{"name":"AIRFLOW__DATABASE__SQL_ALCHEMY_CONN","valueFrom":
  {"secretKeyRef":{"name":"airflow-db-secret","key":"connection"}}}]}]}}'

# Check pod connectivity
kubectl get pod <pod> -n <ns> -o wide
kubectl describe pod <pod> -n <ns> | grep -A10 Events
```
EOF
```

Now create the Word document:
<function_calls>
<invoke name="bash_tool">
<parameter name="command">cat > /home/claude/create_troubleshooting.js << 'EOF'
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        HeadingLevel, BorderStyle, WidthType, ShadingType, AlignmentType,
        LevelFormat } = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const headerShade = { fill: "2B5797", type: ShadingType.CLEAR };
const altShade = { fill: "EEF2F7", type: ShadingType.CLEAR };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text, bold: true, size: 32, color: "2B5797", font: "Arial" })],
    spacing: { before: 400, after: 200 }
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, bold: true, size: 26, color: "1F3864", font: "Arial" })],
    spacing: { before: 320, after: 160 }
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    children: [new TextRun({ text, bold: true, size: 24, color: "C0392B", font: "Arial" })],
    spacing: { before: 240, after: 120 }
  });
}

function label(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, size: 22, color: "1F3864", font: "Arial" })],
    spacing: { before: 160, after: 80 }
  });
}

function body(text) {
  return new Paragraph({
    children: [new TextRun({ text, size: 20, font: "Arial" })],
    spacing: { before: 60, after: 60 }
  });
}

function code(text) {
  return new Paragraph({
    children: [new TextRun({ text, size: 18, font: "Courier New", color: "C0392B" })],
    spacing: { before: 40, after: 40 },
    indent: { left: 720 },
    shading: { fill: "F4F4F4", type: ShadingType.CLEAR }
  });
}

function divider() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "2B5797", space: 1 } },
    spacing: { before: 200, after: 200 }
  });
}

function makeTable(headers, rows) {
  const colCount = headers.length;
  const colWidth = Math.floor(9360 / colCount);
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: Array(colCount).fill(colWidth),
    rows: [
      new TableRow({
        children: headers.map(h => new TableCell({
          borders, shading: headerShade,
          width: { size: colWidth, type: WidthType.DXA },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [new TextRun({ text: h, bold: true, size: 20, color: "FFFFFF", font: "Arial" })] })]
        }))
      }),
      ...rows.map((row, ri) => new TableRow({
        children: row.map(cell => new TableCell({
          borders,
          shading: ri % 2 === 0 ? { fill: "FFFFFF", type: ShadingType.CLEAR } : altShade,
          width: { size: colWidth, type: WidthType.DXA },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [new TextRun({ text: cell, size: 18, font: "Arial" })] })]
        }))
      }))
    ]
  });
}

const issues = [
  {
    num: 1, phase: "Phase 1", title: "Duplicate Provider Block in Terraform",
    error: 'Error: Duplicate provider configuration\non main.tf line 36: provider "azurerm" {\nA default (non-aliased) provider configuration was already given at main.tf:23',
    cause: 'cat >> appended a second provider "azurerm" block to main.tf instead of replacing the existing one.',
    fix: 'Rewrote main.tf cleanly using cat > (overwrite) instead of cat >> (append). Used Python str.replace() for targeted edits.',
    lesson: 'Always use cat > for full file rewrites. Use cat >> only for intentional appends. When editing Terraform files, prefer Python str.replace() for targeted edits over shell appends.'
  },
  {
    num: 2, phase: "Phase 1", title: "AKS Kubernetes Version Not Supported (LTS-only)",
    error: 'K8sVersionNotSupported: Managed cluster is on version 1.29/1.30/1.31 which is only available for Long-Term Support (LTS).',
    cause: 'Free tier Azure subscriptions only support LTS versions of Kubernetes. Pinning to a specific version without checking regional support caused repeated failures across versions 1.29, 1.30, 1.31, 1.32.',
    fix: 'Removed the kubernetes_version pin entirely — AKS auto-selects the latest supported version. Cluster deployed on v1.34.7.',
    lesson: 'Never hardcode Kubernetes versions without first running: az aks get-versions --location <region>. On free tier subscriptions, let AKS choose the default version.'
  },
  {
    num: 3, phase: "Phase 1", title: "Key Vault — SubnetsHaveNoServiceEndpointsConfigured",
    error: 'VirtualNetworkNotValid: Subnets snet-aks do not have ServiceEndpoints for Microsoft.KeyVault resources configured.',
    cause: 'Key Vault network ACL referenced the AKS subnet but the subnet had no Microsoft.KeyVault service endpoint configured.',
    fix: 'Added service_endpoints = ["Microsoft.KeyVault", "Microsoft.Storage"] to the AKS subnet in networking/main.tf.',
    lesson: 'When restricting Key Vault or Storage to a specific subnet via network ACLs, the subnet must have the corresponding service endpoint enabled. Service endpoints and private endpoints serve different purposes.'
  },
  {
    num: 4, phase: "Phase 1", title: "PostgreSQL — ConflictingPublicNetworkAccess and VNet",
    error: 'ConflictingPublicNetworkAccessAndVirtualNetworkConfiguration: Public Network Access is not supported along with Virtual Network feature.',
    cause: 'PostgreSQL Flexible Server cannot have both VNet integration (delegated_subnet_id) and public_network_access_enabled = true simultaneously.',
    fix: 'Set public_network_access_enabled = false explicitly in the PostgreSQL Terraform module.',
    lesson: 'Azure PostgreSQL Flexible Server has two mutually exclusive networking modes: public access with firewall rules OR private VNet integration. Choose one at creation time.'
  },
  {
    num: 5, phase: "Phase 1", title: "PostgreSQL — LocationIsOfferRestricted (eastus)",
    error: 'LocationIsOfferRestricted: Subscriptions are restricted from provisioning in location eastus.',
    cause: 'Free tier Azure subscriptions cannot provision PostgreSQL Flexible Server in eastus.',
    fix: 'Moved PostgreSQL to canadacentral by introducing a postgresql_location variable. Also removed VNet integration since cross-region VNet integration is not supported.',
    lesson: 'Free tier subscriptions have regional restrictions on specific services. Always test service availability before committing to a region in Terraform.'
  },
  {
    num: 6, phase: "Phase 1", title: "PostgreSQL — Missing Subnet Delegation",
    error: 'OperationFailed: The subnet snet-private-endpoints is missing required delegations Microsoft.DBforPostgreSQL/flexibleServers',
    cause: 'PostgreSQL Flexible Server with VNet integration requires a dedicated subnet with delegation. It cannot share the private endpoints subnet.',
    fix: 'Added a new azurerm_subnet.postgresql resource with the required delegation block in networking/main.tf. Added output and wired to postgresql module.',
    lesson: 'PostgreSQL Flexible Server subnet delegation is exclusive — no other resources can use the same subnet. Always create a dedicated subnet for PostgreSQL VNet integration.'
  },
  {
    num: 7, phase: "Phase 1", title: "Storage Containers — 403 AuthorizationFailure",
    error: 'checking for existing Container "raw-documents": unexpected status 403 AuthorizationFailure: This request is not authorized.',
    cause: 'Storage account had public_network_access_enabled = false. Terraform running from a laptop could not create containers because the local machine IP was not whitelisted before network rules applied.',
    fix: 'Set public_network_access_enabled = true during bootstrap. Added TF_VAR_allowed_ip to storage network rules. Added depends_on = [azurerm_storage_account_network_rules.main] to all container resources.',
    lesson: 'This is the classic bootstrap chicken-and-egg problem. The production pattern is to run Terraform from inside the private network (CI/CD agent in VNet). For bootstrap, temporarily allow public access with IP restriction.'
  },
  {
    num: 8, phase: "Phase 1", title: "AKS VM SKU Not Allowed (Free Tier Restriction)",
    error: 'BadRequest: The VM size Standard_B2s / Standard_D4s_v3 is not allowed in your subscription in location eastus.',
    cause: 'Free tier Azure subscriptions in eastus only allow DC/EC/FX/HB/M/NC series VMs for AKS. Standard D/B/F series are not permitted.',
    fix: 'Changed all node pool VM sizes to Standard_DC2s_v3 (confidential compute series) which is allowed on this subscription type.',
    lesson: 'Always run az vm list-usage --location <region> before designing node pool VM sizes. Document subscription-level VM family restrictions in Architecture Decision Records (ADRs).'
  },
  {
    num: 9, phase: "Phase 1", title: "vCPU Quota Exhaustion",
    error: 'ErrCode_InsufficientVCPUQuota: Insufficient regional vcpu quota. left regional vcpu quota 0, requested quota 4.',
    cause: 'Standard DCSv3 Family quota was 4 vCPUs total. System pool (2x DC2s_v3 = 4 vCPUs) consumed entire quota. No vCPUs left for CPU node pool.',
    fix: 'Scaled system pool from 2 nodes to 1 node (freed 2 vCPUs). Deleted and recreated CPU node pool with DC2s_v3 (2 vCPUs) instead of DC4s_v3 (4 vCPUs). Set CPU node pool min_count = 0.',
    lesson: 'On free tier subscriptions, vCPU quota per VM family is very limited (typically 4 per family). Plan node pool VM sizes around available quota. Use az vm list-usage to check quotas before designing the cluster.'
  },
  {
    num: 10, phase: "Phase 1", title: "Key Vault Secrets — Race Condition (AccessDenied)",
    error: 'The user does not have secrets get permission on key vault kv-llmops-prod. InnerError: AccessDenied',
    cause: 'Terraform tried to create Key Vault secrets before the access policy resource was fully applied. Implicit dependency was not detected because secrets reference key_vault_id (the vault), not the access policy resource.',
    fix: 'Added explicit depends_on = [azurerm_key_vault_access_policy.terraform_caller] to all three secret resources.',
    lesson: 'Terraform implicit dependencies only work when resources reference each other directly. When a resource depends on a side effect of another resource (like an access policy granting permissions), use explicit depends_on.'
  },
  {
    num: 11, phase: "Phase 2", title: "Airflow Helm — ServiceAccount Ownership Conflict",
    error: 'ServiceAccount "ingestion-sa" exists and cannot be imported: missing key "app.kubernetes.io/managed-by": must be set to "Helm"',
    cause: 'ServiceAccount was created manually with kubectl before Helm install. Helm requires ownership labels/annotations on resources it manages.',
    fix: 'Deleted the manually created ServiceAccount and let Helm recreate it. Re-annotated with workload identity client ID after Helm deploy.',
    lesson: 'Never manually create Kubernetes resources that Helm will also manage. Either manage entirely outside Helm or let Helm own them from the start.'
  },
  {
    num: 12, phase: "Phase 2", title: "Airflow Init Container Stuck — Missing DB Migration",
    error: 'All Airflow pods stuck in Init:0/1 indefinitely. Init container running airflow db check-migrations never completing.',
    cause: 'Airflow init container waits for database migrations before starting. Migrations had never been run — the airflow database existed but had no schema tables.',
    fix: 'Ran airflow db migrate as a one-off Kubernetes pod using kubectl run with the airflow-db-secret mounted as env var.',
    lesson: 'Airflow Helm chart does not run db migrate automatically unless migrateDatabaseJob.enabled: true is set. Always check Helm chart defaults for database migration behavior.'
  },
  {
    num: 13, phase: "Phase 2", title: "kubectl logs — 504 Gateway Timeout on Port 10250",
    error: 'proxy error from localhost:9443 while dialing 10.1.0.33:10250, code 504: 504 Gateway Timeout',
    cause: 'NSG on AKS subnet had a deny-all-inbound rule at priority 4096. This blocked kubelet API on port 10250 which kubectl logs, kubectl exec, and kubectl port-forward rely on.',
    fix: 'Added inbound NSG rule to allow port 10250 from VirtualNetwork to VirtualNetwork at priority 200.',
    lesson: 'AKS requires port 10250 (kubelet API) to be accessible within the VNet. Never add a blanket deny-all-inbound NSG rule without first adding all required AKS ports.'
  },
  {
    num: 14, phase: "Phase 2", title: "CoreDNS — External DNS Resolution Failure from Pods",
    error: 'connection timed out; no servers could be reached. nslookup: cannot resolve postgres.database.azure.com',
    cause: 'CoreDNS used forward . /etc/resolv.conf. The AKS-managed NSG on node NICs was blocking DNS traffic. The custom subnet NSG rules had no effect on pod-level traffic.',
    fix: 'Patched CoreDNS ConfigMap to forward directly to Azure DNS 168.63.129.16 instead of /etc/resolv.conf. Restarted CoreDNS deployment.',
    lesson: 'Azure 168.63.129.16 is a platform DNS server that must always be reachable from AKS nodes. Never block outbound traffic to this IP. Always include an explicit allow rule for it in AKS network designs.'
  },
  {
    num: 15, phase: "Phase 2", title: "PostgreSQL Firewall — Private IPs Not Supported",
    error: 'Pod connection to PostgreSQL timed out even with firewall rule covering 10.1.0.0/16 (AKS pod subnet).',
    cause: 'Azure PostgreSQL Flexible Server firewall rules do not support RFC1918 private IP ranges. Rules with private IPs are accepted by the API but never applied.',
    fix: 'Added the special Azure convention firewall rule 0.0.0.0 to 0.0.0.0 which means "allow all Azure-internal services".',
    lesson: 'PostgreSQL Flexible Server firewall rules only work for public IPs. For AKS pod access without VNet integration, use the 0.0.0.0/0.0.0.0 Azure services rule. For production, use VNet integration with subnet delegation.'
  },
  {
    num: 16, phase: "Phase 2", title: "AKS-Managed NSG in MC_* Resource Group",
    error: 'Custom NSG rules on user-created NSG had no effect on pod outbound traffic. Port 5432 still timed out.',
    cause: 'AKS creates its own NSG (aks-agentpool-XXXXXXXX-nsg) in the MC_* node resource group attached to node NICs. This controls actual pod traffic. The subnet NSG in the user RG applies at subnet level only.',
    fix: 'Added port 5432 outbound rule directly to the AKS-managed NSG in the MC_* resource group.',
    lesson: 'AKS manages two NSGs: one on the subnet (user-controlled) and one on node NICs (AKS-managed in MC_* RG). Pod-level traffic is governed by the NIC NSG. Manual changes may be overwritten during node pool upgrades.'
  },
  {
    num: 17, phase: "Phase 2", title: "Airflow Helm — Redis Deployed with KubernetesExecutor",
    error: 'Helm install timed out waiting for airflow-redis StatefulSet even though KubernetesExecutor was configured.',
    cause: 'Default Helm values had Redis enabled. KubernetesExecutor does not use Redis but the chart deployed it unless explicitly disabled.',
    fix: 'Added redis.enabled: false and workers.replicas: 0 to values.yaml.',
    lesson: 'Always review Helm chart default values with helm show values <chart> before deploying. Many charts enable components by default that may not be needed for your deployment pattern.'
  }
];

const summaryRows = [
  ["1", "Check AKS supported versions per region before pinning: az aks get-versions"],
  ["2", "Check VM quota per family before designing node pools: az vm list-usage"],
  ["3", "Free tier subscriptions have VM family, region, and service restrictions — test early"],
  ["4", "Never block 168.63.129.16 — Azure DNS, IMDS, and health probes depend on it"],
  ["5", "PostgreSQL Flexible Server firewall rules do not support private RFC1918 IPs"],
  ["6", "AKS manages its own NSG in MC_* RG — subnet NSG alone is not enough for pod traffic"],
  ["7", "Terraform bootstrap is a chicken-and-egg problem — allow public access temporarily"],
  ["8", "Airflow db migrate must run before pods start — Helm does not do it automatically"],
  ["9", "CoreDNS forward to /etc/resolv.conf can fail if NSG blocks DNS — pin to 168.63.129.16"],
  ["10", "Never manually create resources that Helm manages — let Helm own them from the start"],
  ["11", "PostgreSQL + VNet integration requires dedicated subnet with delegation — no sharing"],
  ["12", "Use cat > for file rewrites, cat >> only for appends — prevent duplicate Terraform blocks"],
  ["13", "Always run terraform validate after every module change before terraform plan"],
  ["14", "Remote state backend must be bootstrapped manually before terraform init with real backend"],
  ["15", "sensitive = true in Terraform variables requires multi-line block syntax"]
];

const children = [
  new Paragraph({
    children: [new TextRun({ text: "LLMOps Platform — Azure", bold: true, size: 48, color: "2B5797", font: "Arial" })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 400, after: 200 }
  }),
  new Paragraph({
    children: [new TextRun({ text: "Troubleshooting Log — Phase 1 & Phase 2", size: 28, color: "555555", font: "Arial" })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 100 }
  }),
  new Paragraph({
    children: [new TextRun({ text: "Real issues encountered during deployment, root causes, fixes, and lessons learned.", size: 22, color: "666666", font: "Arial", italics: true })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 400 }
  }),
  divider(),
  h1("Overview"),
  body("This document captures every issue encountered during Phase 1 (Azure Infrastructure) and Phase 2 (Data Ingestion Pipeline) deployment of the LLMOps Document Q&A platform. Each issue includes the exact error message, root cause analysis, fix applied, and the lesson learned for future deployments."),
  new Paragraph({ spacing: { before: 200, after: 200 } }),
  makeTable(["#", "Phase", "Issue Title", "Category"], issues.map(i => [
    String(i.num), i.phase, i.title,
    i.num <= 10 ? "Infrastructure" : "Kubernetes/Airflow"
  ])),
  new Paragraph({ spacing: { before: 400 } }),
  divider(),
  h1("Phase 1 — Infrastructure Issues"),
];

issues.filter(i => i.phase === "Phase 1").forEach(issue => {
  children.push(
    h3(`Issue ${issue.num}: ${issue.title}`),
    label("Error"),
    code(issue.error),
    label("Root Cause"),
    body(issue.cause),
    label("Fix Applied"),
    body(issue.fix),
    label("Lesson Learned"),
    body(issue.lesson),
    divider()
  );
});

children.push(h1("Phase 2 — Data Ingestion Pipeline Issues"));

issues.filter(i => i.phase === "Phase 2").forEach(issue => {
  children.push(
    h3(`Issue ${issue.num}: ${issue.title}`),
    label("Error"),
    code(issue.error),
    label("Root Cause"),
    body(issue.cause),
    label("Fix Applied"),
    body(issue.fix),
    label("Lesson Learned"),
    body(issue.lesson),
    divider()
  );
});

children.push(
  h1("Summary — Key Lessons"),
  makeTable(["#", "Lesson"], summaryRows),
  new Paragraph({ spacing: { before: 400 } }),
  divider(),
  h1("Useful Diagnostic Commands"),
  h2("AKS & Kubernetes"),
  code("az aks get-versions --location eastus --output table"),
  code("az vm list-usage --location eastus --output table | grep -i standard"),
  code("kubectl get pods -n llmops"),
  code("kubectl describe pod <pod> -n <ns> | grep -A10 Events"),
  code("kubectl get events -n llmops --sort-by=.lastTimestamp | tail -20"),
  h2("Network Diagnostics"),
  code("az network nsg list --resource-group MC_<rg>_<cluster>_<region> --output table"),
  code("az network nsg show --resource-group <rg> --name <nsg> --query securityRules --output table"),
  code("kubectl run dns-test --image=busybox --restart=Never --namespace=llmops -- nslookup <hostname>"),
  h2("PostgreSQL"),
  code("az postgres flexible-server firewall-rule list --resource-group <rg> --name <server> --output table"),
  code("kubectl run pg-test --image=postgres:16 --restart=Never --namespace=llmops -- psql \"postgresql://<user>@<host>/<db>?sslmode=require\" -c \"SELECT 1\""),
  h2("Airflow"),
  code("kubectl get configmap coredns -n kube-system -o yaml"),
  code("helm show values apache-airflow/airflow | grep -A5 redis"),
  code("kubectl exec -it deployment/airflow-webserver -n llmops -- airflow users list"),
  new Paragraph({
    children: [new TextRun({ text: `Generated: ${new Date().toDateString()} | Author: Himanshu Singh | Project: LLMOps Doc Q&A on Azure`, size: 16, color: "888888", font: "Arial", italics: true })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 600 }
  })
);

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: "2B5797", font: "Arial" },
        paragraph: { spacing: { before: 400, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, color: "1F3864", font: "Arial" },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: "C0392B", font: "Arial" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 2 } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    children
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync('/mnt/user-data/outputs/TROUBLESHOOTING.docx', buffer);
  console.log('DONE');
});
EOF
node /home/claude/create_troubleshooting.js