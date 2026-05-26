import os
from dataclasses import dataclass

@dataclass
class RAGConfig:
    # Embedding — must match ingestion pipeline model
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    embedding_dim:   int = 768

    # PostgreSQL pgvector (vectorstore DB)
    pg_host:     str = os.environ.get("POSTGRES_HOST", "")
    pg_db:       str = "vectorstore"
    pg_user:     str = os.environ.get("POSTGRES_USER", "llmopsadmin")
    pg_password: str = os.environ.get("POSTGRES_PASSWORD", "")
    pg_port:     int = 5432

    # Retrieval tuning
    dense_top_k:  int = 20   # Candidates from pgvector ANN
    sparse_top_k: int = 20   # Candidates from BM25
    rerank_top_k: int = 5    # Final chunks after reranker

    # Reranker model
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # vLLM endpoint (Phase 4 — running in same namespace)
    vllm_endpoint: str = os.environ.get(
        "VLLM_ENDPOINT",
        "http://vllm-service.llmops.svc.cluster.local:8000/v1"
    )
    llm_model:       str = "mistral-7b-instruct"
    llm_max_tokens:  int = 1024
    llm_temperature: float = 0.1   # Low temp for factual Q&A

    # Redis cache
    redis_host:    str = os.environ.get("REDIS_HOST", "redis-service.llmops.svc.cluster.local")
    redis_port:    int = 6379
    cache_ttl_sec: int = 3600  # 1 hour TTL

    # Azure Key Vault (secrets injected via env by CSI driver)
    azure_client_id: str = os.environ.get("AZURE_CLIENT_ID", "87c2c4e4-3998-4798-a9fa-1d22dc63c49a")

config = RAGConfig()