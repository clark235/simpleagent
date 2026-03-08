# VNET Deployment Record — Azure AI Foundry VNet Demo

**Deployed:** 2026-03-08  
**By:** Clark (automated via OpenClaw agent platform)  
**Subscription:** 50948ce7-018f-4a26-9cf3-2b4f982b5358  
**Tenant:** d7cf5520-4aef-4037-a839-14b69617025e

---

## Resource Group

| Field | Value |
|-------|-------|
| Name | `rg-simpleagent-vnet` |
| Region | `eastus` |
| Tags | owner=clark, purpose=simpleagent-vnet-demo, project=simpleagent |

---

## Virtual Network

| Resource | Value |
|----------|-------|
| VNet Name | `vnet-simpleagent` |
| Address Space | `192.168.0.0/16` |
| **snet-agents** | `192.168.0.0/24` — delegated to `Microsoft.App/environments` |
| **snet-resources** | `192.168.1.0/24` — private endpoint NICs |
| **snet-vm** | `192.168.2.0/24` — Windows VM |

---

## AI Services Account (New Foundry / Responses API)

| Field | Value |
|-------|-------|
| Name | `clark-simpleagent-vnet-ai` |
| Kind | AIServices, SKU: S0 |
| Custom Domain | `clark-simpleagent-vnet` |
| AI Foundry API | `https://clark-simpleagent-vnet.services.ai.azure.com/` |
| OpenAI (Legacy) | `https://clark-simpleagent-vnet.openai.azure.com/` |
| Cognitive Services | `https://clark-simpleagent-vnet.cognitiveservices.azure.com/` |
| Public Network Access | **Disabled** |
| Private Endpoint | `pe-clark-ai-services` → `192.168.1.4` |
| Managed Identity | `9a51d3b7-37b3-4202-93de-8f721e236621` |
| **gpt-4o deployment** | Model: `gpt-4o` v2024-11-20, Standard 10K TPM |

### Foundry Project (New Foundry)

> **Action Required:** The New Foundry project must be created from inside the VNet (via the VM)  
> since the AI Services account has public access disabled.

To create from the VM:
1. RDP to `168.62.60.137`
2. Open a browser and navigate to `https://ai.azure.com`
3. Connect to `clark-simpleagent-vnet-ai`
4. Create a new project — the endpoint will be:
   `https://clark-simpleagent-vnet.services.ai.azure.com/api/projects/<your-project-name>`
5. Register the AI Search connection as `clark-search-vnet`
6. Update `FOUNDRY_PROJECT_ENDPOINT` in `.env`

---

## Classic Foundry Hub (Assistants API)

| Field | Value |
|-------|-------|
| Hub Name | `clark-simpleagent-hub` |
| Kind | Hub (MachineLearningServices) |
| Hub ARM ID | `/subscriptions/50948ce7-018f-4a26-9cf3-2b4f982b5358/resourceGroups/rg-simpleagent-vnet/providers/Microsoft.MachineLearningServices/workspaces/clark-simpleagent-hub` |
| Discovery URL | `https://eastus.api.azureml.ms/discovery` |
| Portal | `https://ml.azure.com` |

### Classic Foundry Project

| Field | Value |
|-------|-------|
| Project Name | `clark-simpleagent-project` |
| Project ARM ID | `/subscriptions/50948ce7-018f-4a26-9cf3-2b4f982b5358/resourceGroups/rg-simpleagent-vnet/providers/Microsoft.MachineLearningServices/workspaces/clark-simpleagent-project` |
| **Classic Agents Endpoint** | `https://eastus.api.azureml.ms` |
| mlflow URI | `azureml://eastus.api.azureml.ms/mlflow/v1.0/subscriptions/50948ce7-018f-4a26-9cf3-2b4f982b5358/resourceGroups/rg-simpleagent-vnet/providers/Microsoft.MachineLearningServices/workspaces/clark-simpleagent-project` |

**Note:** The classic `AgentsClient` uses endpoint `https://eastus.api.azureml.ms` and authenticates  
with `DefaultAzureCredential`. The project is addressed by name in the request context.

---

## Azure AI Search

| Field | Value |
|-------|-------|
| Name | `clark-simpleagent-search-vnet` |
| SKU | Basic |
| Region | eastus |
| Endpoint | `https://clark-simpleagent-search-vnet.search.windows.net` |
| Public Network Access | **Disabled** |
| Trusted Services Bypass | **AzureServices** (Foundry can reach Search via trusted backbone) |
| Auth Options | `aadOrApiKey` (RBAC + key auth both enabled) |
| Private Endpoint | `pe-clark-search` → `192.168.1.8` |

### AI Search Index

| Field | Value |
|-------|-------|
| Index Name | `simpleagent-repo-index` |
| Documents | **61 chunks** from 7 repo files |
| Semantic Config | `default` (semantic search enabled) |
| Analyzer | `en.microsoft` on content field |

### RBAC Assignments on Search

| Principal | Role |
|-----------|------|
| AI Services MSI (`9a51d3b7-37b3-4202-93de-8f721e236621`) | Search Index Data Reader |
| AI Services MSI | Search Index Data Contributor |
| Current user (`8f7a4f8a-75d9-4214-9d4f-252686f699ea`) | Search Index Data Contributor |

---

## Storage Account

| Field | Value |
|-------|-------|
| Name | `clarksimplevnetstor` |
| SKU | Standard_LRS |
| Public Network Access | **Disabled** |
| Private Endpoint | `pe-clark-storage-blob` → `192.168.1.7` |

---

## Windows VM

| Field | Value |
|-------|-------|
| VM Name | `vm-sagent-demo` |
| Computer Name | `sagentdemo` |
| Size | Standard_B2s |
| Image | Windows Server 2022 Datacenter |
| Subnet | `snet-vm` (192.168.2.0/24) |
| **Public IP** | **168.62.60.137** |
| Username | `demoadmin` |
| Password | `DemoAdmin#fd37f0a4f802Ax9!` |
| NSG | `nsg-snet-vm` — RDP (3389) open inbound from any |

### Software Installed on VM

- Python 3.12.10
- Git 2.53.0
- `azure-ai-projects==2.0.0`
- `azure-ai-agents==1.1.0`
- `azure-identity`
- `python-dotenv`
- simpleagent repo cloned to `C:\simpleagent`

---

## Private DNS Zones (all linked to vnet-simpleagent)

| Zone | DNS A Record | Private IP |
|------|-------------|-----------|
| `privatelink.cognitiveservices.azure.com` | `clark-simpleagent-vnet` | `192.168.1.4` |
| `privatelink.openai.azure.com` | `clark-simpleagent-vnet` | `192.168.1.4` |
| `privatelink.search.windows.net` | `clark-simpleagent-search-vnet` | `192.168.1.8` |
| `privatelink.blob.core.windows.net` | `clarksimplevnetstor` | `192.168.1.7` |

---

## DNS Verification (from outside VNet)

```
$ nslookup clark-simpleagent-search-vnet.search.windows.net
clark-simpleagent-search-vnet.search.windows.net → clark-simpleagent-search-vnet.privatelink.search.windows.net
  → azsubci.eastus.cloudapp.azure.com
  → 20.120.120.131 (public Azure IP — expected from outside VNet)
```

> **Note:** From outside the VNet, the DNS resolves to a public Azure IP (correct behavior).  
> From inside the VNet (on the VM), it will resolve to `192.168.1.8` via the private DNS zone.

---

## Deployment Steps Executed

1. ✅ Resource group created: `rg-simpleagent-vnet` in `eastus`
2. ✅ VNet created: `vnet-simpleagent` with 3 subnets
3. ✅ snet-agents delegated to `Microsoft.App/environments`
4. ✅ 4 private DNS zones created and linked to VNet
5. ✅ AI Services account created with custom domain `clark-simpleagent-vnet`
6. ✅ AI Services public network access disabled
7. ✅ gpt-4o deployed (Standard, 10K TPM)
8. ✅ AI Search created with `publicNetworkAccess=Disabled`, `aadOrApiKey`, trusted services bypass
9. ✅ Storage account created with `publicNetworkAccess=Disabled`
10. ✅ Classic Foundry Hub created: `clark-simpleagent-hub`
11. ✅ Classic Foundry Project created: `clark-simpleagent-project`
12. ✅ Private endpoints created for: AI Services, Search, Storage
13. ✅ Private DNS A records created for all endpoints
14. ✅ RBAC assigned: AI Services MSI + current user → Search Index Data Contributor
15. ✅ Search index created: `simpleagent-repo-index` with 61 documents
16. ✅ Windows VM deployed: `vm-sagent-demo` at `168.62.60.137`
17. ✅ VM configured with Python 3.12, Git, azure-ai packages, simpleagent repo

---

## Known Issues / Follow-up Required

### 1. New Foundry Project (ai.azure.com)
The AI Services account has public access disabled, so the project endpoint couldn't be  
created via CLI from outside the VNet. **Action Required:**
- RDP to `168.62.60.137`
- Navigate to `https://ai.azure.com` in the browser (routes through the VNet)
- Create a new project under `clark-simpleagent-vnet-ai`
- Register AI Search as a connection named `clark-search-vnet`
- Update `FOUNDRY_PROJECT_ENDPOINT` in `C:\simpleagent\.env`

### 2. Azure CLI not installed on VM
The automated setup script timed out before installing Azure CLI. For az CLI auth on the VM:
- Install from: https://aka.ms/installazurecliwindows
- Or use `az login` with device code flow

### 3. Search Admin Key needed for indexing from VM
When running `index_repo.py` on the VM, set:
```powershell
$env:AZURE_SEARCH_ADMIN_KEY = "XyUNC2ft..."  # Get from Azure portal
```

### 4. Index is pre-populated from deployment
The search index was pre-populated with 61 document chunks during deployment.  
Run `index_repo.py` from the VM to re-index after any file changes.

---

## Verification Commands (run from inside VNet or with public access temporarily enabled)

```bash
# 1. Search public access
az search service show --name clark-simpleagent-search-vnet --query publicNetworkAccess
# Expected: "Disabled"

# 2. DNS link check
az network private-dns link vnet list --zone-name privatelink.search.windows.net
# Expected: shows link-vnet-simpleagent-... linked to vnet-simpleagent

# 3. Trusted services bypass
az search service show --name clark-simpleagent-search-vnet --query networkRuleSet.bypass
# Expected: "AzureServices"

# 4. Document count (from VM inside VNet)
curl -H "api-key: <key>" "https://clark-simpleagent-search-vnet.search.windows.net/indexes/simpleagent-repo-index/docs/$count?api-version=2024-07-01"
# Expected: 61
```
