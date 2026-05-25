cat > README.md << 'README'
# LLMOps Platform — Document Q&A on Azure

Production-grade LLMOps platform for Document Q&A built on Azure Kubernetes Service.
Covers the full LLMOps lifecycle: data ingestion, RAG pipeline, LLM serving, fine-tuning, evaluation, CI/CD, and observability.

---

## Architecture Overview

    Documents (PDF/DOCX/HTML)
           ↓
    ADLS Gen2 (raw-documents container)
           ↓
    Airflow DAG on AKS (KubernetesExecutor)
           ↓
    Azure Document Intelligence (OCR + layout extraction)
           ↓
    Text Cleaner → RecursiveCharacterTextSplitter (512/64)
           ↓
    Embedding Model: all-mpnet-base-v2 (768-dim)
           ↓
    pgvector HNSW Index (vectorstore DB)
           ↓
    RAG Pipeline: FastAPI + LangChain + Hybrid Retrieval   [Phase 3]
           ↓
    vLLM Serving: Mistral-7B-Instruct (AKS GPU node)      [Phase 4]
           ↓
    Response + Source Citations → User

---

## Tech Stack

| Layer                   | Technology                                          |
|-------------------------|-----------------------------------------------------|
| Cloud                   | Microsoft Azure                                     |
| Container Orchestration | AKS (Azure Kubernetes Service) v1.34                |
| Infrastructure as Code  | Terraform 1.6+ (modular, remote state)              |
| Container Registry      | Azure Container Registry (ACR) Premium              |
| Storage                 | ADLS Gen2 — 5 containers (raw/chunks/models/training/eval) |
| Database                | PostgreSQL 16 Flexible Server + pgvector extension  |
| Vector Search           | pgvector HNSW index (m=16, ef_construction=64)      |
| Secrets Management      | Azure Key Vault (purge protection, soft delete)     |
| Pipeline Orchestration  | Apache Airflow 2.8.3 (KubernetesExecutor)           |
| Document Extraction     | Azure Document Intelligence (prebuilt-layout)       |
| Embedding Model         | sentence-transformers/all-mpnet-base-v2 (768-dim)   |
| Identity                | Azure Workload Identity (OIDC federation, zero credentials) |
| DNS                     | CoreDNS → Azure DNS 168.63.129.16                   |

---

## Repository Structure

    Azure-LLMOps/
    ├── infra/
    │   ├── modules/
    │   │   ├── aks/                    # AKS cluster, system/cpu/gpu node pools
    │   │   ├── networking/             # VNet, subnets, NSGs, private DNS zones
    │   │   ├── storage/                # ADLS Gen2, 5 containers, private endpoint
    │   │   ├── keyvault/               # Key Vault, secrets, access policies
    │   │   ├── postgresql/             # PostgreSQL Flexible Server, pgvector, DBs
    │   │   ├── acr/                    # Container Registry, geo-replication
    │   │   └── workload-identity/      # Managed identities, federated credentials, RBAC
    │   ├── live/
    │   │   ├── dev/                    # Dev environment (empty - future)
    │   │   └── prod/                   # Production Terraform root module
    │   │       ├── main.tf             # Module wiring
    │   │       ├── variables.tf        # Input variables
    │   │       ├── outputs.tf          # Output values
    │   │       └── terraform.tfvars    # Non-sensitive defaults
    │   ├── k8s/
    │   │   └── airflow/
    │   │       ├── values.yaml         # Helm chart values
    │   │       └── release.sh          # Idempotent deploy script
    │   └── scripts/
    │       ├── bootstrap_subscription.sh   # Day-0: register Azure resource providers
    │       └── bootstrap_tfstate.sh        # Day-0: create remote state backend
    ├── services/
    │   └── ingestion/
    │       ├── config/
    │       │   └── settings.py         # Centralized config (env-driven)
    │       ├── dags/
    │       │   └── document_ingestion_dag.py  # Airflow DAG (4-stage pipeline)
    │       ├── operators/
    │       │   ├── extract_operator.py  # Azure Document Intelligence OCR
    │       │   ├── chunk_operator.py    # RecursiveCharacterTextSplitter
    │       │   ├── embed_operator.py    # Batch embedding (all-mpnet-base-v2)
    │       │   └── index_operator.py    # pgvector upsert (idempotent)
    │       ├── utils/
    │       │   ├── hash_utils.py        # SHA256 doc hash, chunk ID generation
    │       │   ├── text_cleaner.py      # Noise removal, normalization
    │       │   └── metadata.py          # Chunk metadata builder
    │       ├── tests/
    │       │   └── test_pipeline.py     # Unit tests (Phase 7)
    │       ├── Dockerfile               # Multi-stage, non-root, model pre-cached
    │       ├── event_grid_trigger.py    # FastAPI webhook for blob events
    │       └── requirements.txt
    └── README.md

---

## Phases

| Phase | Description                                              | Status       |
|-------|----------------------------------------------------------|--------------|
| 1     | Azure Infrastructure (AKS, Storage, PostgreSQL, ACR, KV) | ✅ Complete  |
| 2     | Data Ingestion Pipeline (Airflow + Doc Intelligence + pgvector) | ✅ Complete |
| 3     | RAG Pipeline (FastAPI + LangChain + hybrid retrieval)    | 🔜 Next      |
| 4     | LLM Serving (vLLM + Mistral-7B on GPU node pool)         | 🔜           |
| 5     | Fine-Tuning Pipeline (QLoRA on AKS GPU)                  | 🔜           |
| 6     | Evaluation Framework (RAGAS + DeepEval)                  | 🔜           |
| 7     | CI/CD for Models (GitHub Actions + ArgoCD + canary)      | 🔜           |
| 8     | Observability (Langfuse + Prometheus + Grafana + Loki)   | 🔜           |
| 9     | Drift Detection + Retraining Triggers                    | 🔜           |
| 10    | Security Hardening + Production Readiness                | 🔜           |

---

## Phase 1 — Infrastructure

### Azure Resources Deployed

| Resource | Name | Details |
|---|---|---|
| Resource Group | rg-llmops-prod | eastus |
| AKS Cluster | aks-llmops-prod | v1.34, Azure CNI, Workload Identity |
| System Node Pool | Standard_DC2s_v3 | 1 node, CriticalAddonsOnly taint |
| CPU Node Pool | Standard_DC2s_v3 | 1 node, node-type=cpu label |
| GPU Node Pool | Standard_NC24ads_A100_v4 | 0→2 nodes (scale to zero) |
| Container Registry | acrllmopsprod | Premium, geo-replicated westus2 |
| Storage Account | stllmopsprod | ADLS Gen2, ZRS, soft delete 30d |
| Key Vault | kv-llmops-prod | Standard, purge protection 90d |
| PostgreSQL | psql-llmops-prod | v16, B1ms, canadacentral, pgvector |
| Log Analytics | law-llmops-prod | 30d retention, PerGB2018 |

### Terraform Remote State

    Backend:  Azure Storage
    Account:  llmopshs825412
    Container: tfstate
    Key:      prod/terraform.tfstate
    Features: versioning enabled, soft delete 30d, CanNotDelete lock

### Workload Identity

Four managed identities with least-privilege RBAC:

| Identity | Role | Scope |
|---|---|---|
| mi-rag-api-prod | Storage Blob Data Reader | stllmopsprod |
| mi-rag-api-prod | Key Vault Secrets User | kv-llmops-prod |
| mi-vllm-prod | Storage Blob Data Reader | stllmopsprod |
| mi-finetuning-prod | Storage Blob Data Contributor | stllmopsprod |
| mi-ingestion-prod | Storage Blob Data Contributor | stllmopsprod |

---

## Phase 2 — Data Ingestion Pipeline

### Pipeline Flow

    1. Document uploaded to ADLS Gen2 (raw-documents)
    2. Event Grid triggers Airflow DAG via FastAPI webhook
    3. ExtractOperator: Azure Document Intelligence (prebuilt-layout)
       - OCR + reading order preservation
       - Table extraction as structured content
       - Page-by-page text with boundaries
    4. ChunkOperator: RecursiveCharacterTextSplitter
       - chunk_size=512, chunk_overlap=64
       - Separators: paragraph → sentence → word
       - Filters chunks < 50 chars or < 20% alphabetic
    5. EmbedOperator: all-mpnet-base-v2 (768-dim)
       - Batch size 32, L2 normalized
       - Model pre-cached in Docker image
    6. IndexOperator: pgvector upsert
       - HNSW index (m=16, ef_construction=64)
       - JSONB metadata index for filtered retrieval
       - Idempotent: ON CONFLICT DO UPDATE

### Idempotency

Every pipeline run is safe to re-run:
- Document hash (SHA256) detects unchanged documents
- Chunk ID = MD5(doc_hash:chunk_index) — deterministic
- pgvector upsert — no duplicates on re-ingestion

### Airflow Deployment

    Chart:      apache-airflow 1.13.1
    Executor:   KubernetesExecutor
    Namespace:  llmops
    Image:      acrllmopsprod.azurecr.io/ingestion:latest
    Database:   psql-llmops-prod/airflow

### Known Infrastructure Constraints (Free Tier)

    VM Family:   Only DC/EC/NC series allowed in eastus
    vCPU Quota:  8 total (4 system + 4 CPU node)
    PostgreSQL:  canadacentral (eastus LocationIsOfferRestricted)
    AKS DNS:     CoreDNS patched to use 168.63.129.16 directly
    PG Firewall: 0.0.0.0/0.0.0.0 rule required for AKS pod access

---

## Prerequisites

    Tool          Version
    -----------   --------
    Azure CLI     2.86+
    Terraform     1.6+
    kubectl       1.28+
    Helm          3.12+
    Docker        24+
    Python        3.11+

---

## Getting Started

### Day 0 — Bootstrap

    # 1. Login to Azure
    az login --use-device-code
    az account set --subscription "<subscription-id>"

    # 2. Register resource providers
    bash infra/scripts/bootstrap_subscription.sh

    # 3. Create Terraform state backend
    bash infra/scripts/bootstrap_tfstate.sh

### Deploy Infrastructure

    # Set sensitive variables
    export TF_VAR_subscription_id="<subscription-id>"
    export TF_VAR_postgresql_password="<password>"
    export TF_VAR_huggingface_token="<hf-token>"
    export TF_VAR_langfuse_secret="<langfuse-secret>"
    export TF_VAR_allowed_ip=$(curl -s https://api.ipify.org)

    # Apply
    cd infra/live/prod
    terraform init
    terraform plan -out=tfplan
    terraform apply "tfplan"

### Deploy Airflow

    # Connect to AKS
    az aks get-credentials --resource-group rg-llmops-prod --name aks-llmops-prod

    # Create secrets
    kubectl create namespace llmops
    kubectl create secret generic ingestion-secrets --namespace llmops \
      --from-literal=POSTGRES_HOST=<pg-fqdn> \
      --from-literal=POSTGRES_USER=llmopsadmin \
      --from-literal=POSTGRES_PASSWORD=<password> \
      --from-literal=AZURE_STORAGE_ACCOUNT=stllmopsprod

    # Deploy
    bash infra/k8s/airflow/release.sh

    # Access UI
    kubectl port-forward svc/airflow-webserver 8080:8080 -n llmops
    # Open http://localhost:8080

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| TF_VAR_subscription_id | Azure Subscription ID | Yes |
| TF_VAR_postgresql_password | PostgreSQL admin password | Yes |
| TF_VAR_huggingface_token | HuggingFace API token | Yes |
| TF_VAR_langfuse_secret | Langfuse secret key | Yes |
| TF_VAR_allowed_ip | Your IP for bootstrap access | Yes |
| AZURE_STORAGE_ACCOUNT | Storage account name | Yes |
| POSTGRES_HOST | PostgreSQL FQDN | Yes |
| DOC_INTELLIGENCE_ENDPOINT | Document Intelligence endpoint | Phase 2 |
| DOC_INTELLIGENCE_KEY | Document Intelligence key | Phase 2 |

---

## Cost Estimate (Phase 1+2, Eastus)

| Resource | SKU | Est. Monthly |
|---|---|---|
| AKS System Node (1×) | DC2s_v3 | ~$140 |
| AKS CPU Node (1×) | DC2s_v3 | ~$140 |
| AKS GPU Node (0 min) | NC24ads_A100_v4 | $0 (scale to zero) |
| PostgreSQL | B1ms, canadacentral | ~$15 |
| ACR Premium | Geo-replicated | ~$50 |
| Storage ZRS | ADLS Gen2 | ~$5 |
| Key Vault | Standard | ~$1 |
| **Total baseline** | | **~$351/month** |

GPU nodes cost ~$3.67/hr only when active (training/inference jobs).

---

## Author

Himanshu Singh (Heman)
Cloud DevOps & AI Engineer
GitHub: Himanshu9001
README