import os
from dataclasses import dataclass, field

@dataclass
class IngestionConfig:
    # Azure Storage — ADLS Gen2
    storage_account_name: str = os.environ.get("AZURE_STORAGE_ACCOUNT", "stllmopsprod")
    raw_container:        str = "raw-documents"
    chunks_container:     str = "processed-chunks"

    # Azure Document Intelligence
    doc_intelligence_endpoint: str = os.environ.get("DOC_INTELLIGENCE_ENDPOINT", "")
    doc_intelligence_key:      str = os.environ.get("DOC_INTELLIGENCE_KEY", "")

    # PostgreSQL pgvector
    pg_host:     str = os.environ.get("POSTGRES_HOST", "")
    pg_db:       str = "vectorstore"
    pg_user:     str = os.environ.get("POSTGRES_USER", "llmopsadmin")
    pg_password: str = os.environ.get("POSTGRES_PASSWORD", "")
    pg_port:     int = 5432

    # Chunking
    chunk_size:     int = 512
    chunk_overlap:  int = 64
    min_chunk_size: int = 50

    # Embedding
    embedding_model:      str = "sentence-transformers/all-mpnet-base-v2"
    embedding_dimension:  int = 768
    embedding_batch_size: int = 32

    # Idempotency
    enable_content_hashing: bool = True

config = IngestionConfig()
