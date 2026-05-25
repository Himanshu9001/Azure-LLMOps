from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from ingestion.operators.extract_operator import ExtractOperator
from ingestion.operators.chunk_operator import ChunkOperator
from ingestion.operators.embed_operator import EmbedOperator
from ingestion.operators.index_operator import IndexOperator
from ingestion.config.settings import config
import os

default_args = {
    "owner":                     "llmops-platform",
    "retries":                   3,
    "retry_delay":               timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay":           timedelta(minutes=60),
    "email_on_failure":          True,
}

with DAG(
    dag_id="document_ingestion_pipeline",
    description="OCR → clean → chunk → embed → pgvector index",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule_interval=None,       # Event-driven — triggered by blob upload
    catchup=False,
    max_active_runs=10,           # Process 10 documents in parallel
    tags=["llmops", "ingestion", "rag"],
    params={
        "blob_name":      "",
        "container_name": "raw-documents",
    }
) as dag:

    start = EmptyOperator(task_id="start")

    extract = ExtractOperator(
        task_id="extract_document",
        blob_name="{{ params.blob_name }}",
        storage_account=config.storage_account_name,
        container_name="{{ params.container_name }}",
        doc_intelligence_endpoint=config.doc_intelligence_endpoint,
        doc_intelligence_key=config.doc_intelligence_key,
    )

    chunk = ChunkOperator(
        task_id="chunk_document",
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        min_chunk_size=config.min_chunk_size,
    )

    embed = EmbedOperator(
        task_id="embed_chunks",
        model_name=config.embedding_model,
        batch_size=config.embedding_batch_size,
    )

    index = IndexOperator(
        task_id="index_chunks",
        pg_host=config.pg_host,
        pg_db=config.pg_db,
        pg_user=config.pg_user,
        pg_password=config.pg_password,
        pg_port=config.pg_port,
    )

    end = EmptyOperator(task_id="end")

    # Linear pipeline — each stage waits for previous
    start >> extract >> chunk >> embed >> index >> end
