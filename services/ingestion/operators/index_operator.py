import json
import logging
import psycopg2
import psycopg2.extras
from airflow.models import BaseOperator

logger = logging.getLogger(__name__)

class IndexOperator(BaseOperator):
    """
    Stage 4 — Upsert embedded chunks into pgvector.

    Uses INSERT ... ON CONFLICT DO UPDATE (upsert):
      - Safe to re-run pipeline on same document
      - No duplicate embeddings
      - Idempotency key: chunk_id (deterministic hash)

    HNSW index for ANN search:
      - Better recall than ivfflat at same latency
      - m=16: connections per node (higher = better recall, more memory)
      - ef_construction=64: build-time search width

    JSONB index for metadata filtering:
      - Query by source_blob, file_type, ingested_at
    """

    def __init__(
        self,
        pg_host:     str,
        pg_db:       str,
        pg_user:     str,
        pg_password: str,
        pg_port:     int = 5432,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.pg_host     = pg_host
        self.pg_db       = pg_db
        self.pg_user     = pg_user
        self.pg_password = pg_password
        self.pg_port     = pg_port

    def execute(self, context: dict) -> dict:
        ti               = context["ti"]
        embedding_result = ti.xcom_pull(task_ids="embed_chunks")
        embedded_chunks  = embedding_result["embedded_chunks"]
        doc_hash         = embedding_result["doc_hash"]

        if not embedded_chunks:
            logger.warning("No chunks to index")
            return {"indexed_chunks": 0}

        conn = psycopg2.connect(
            host=self.pg_host,
            dbname=self.pg_db,
            user=self.pg_user,
            password=self.pg_password,
            port=self.pg_port,
            sslmode="require"
        )

        try:
            with conn.cursor() as cur:
                # Create extension + table + indexes if not exist
                cur.execute("""
                    CREATE EXTENSION IF NOT EXISTS vector;

                    CREATE TABLE IF NOT EXISTS document_chunks (
                        chunk_id   TEXT PRIMARY KEY,
                        text       TEXT NOT NULL,
                        embedding  VECTOR(768) NOT NULL,
                        metadata   JSONB,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_chunks_hnsw
                        ON document_chunks
                        USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64);

                    CREATE INDEX IF NOT EXISTS idx_chunks_metadata
                        ON document_chunks USING gin (metadata);
                """)

                # Batch upsert — all chunks in single transaction
                upsert_sql = """
                    INSERT INTO document_chunks
                        (chunk_id, text, embedding, metadata, updated_at)
                    VALUES %s
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        text       = EXCLUDED.text,
                        embedding  = EXCLUDED.embedding,
                        metadata   = EXCLUDED.metadata,
                        updated_at = NOW();
                """

                records = [
                    (
                        c["chunk_id"],
                        c["text"],
                        c["embedding"],
                        json.dumps(c["metadata"])
                    )
                    for c in embedded_chunks
                ]

                psycopg2.extras.execute_values(
                    cur, upsert_sql, records,
                    template="(%s, %s, %s::vector, %s::jsonb)",
                    page_size=100
                )
                conn.commit()
                logger.info(f"Upserted {len(records)} chunks for doc_hash={doc_hash[:8]}")

        finally:
            conn.close()

        return {"indexed_chunks": len(embedded_chunks), "doc_hash": doc_hash}
