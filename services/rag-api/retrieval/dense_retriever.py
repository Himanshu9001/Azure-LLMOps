import logging
import psycopg2
import psycopg2.extras
from sentence_transformers import SentenceTransformer

from config.settings import config

logger = logging.getLogger(__name__)

class DenseRetriever:
    """
    pgvector ANN search using cosine similarity.

    HNSW index does approximate nearest-neighbor — fast (~5ms) but
    may miss some relevant chunks (that's why we oversample top_k=20
    then rerank down to 5).

    L2-normalized embeddings → cosine similarity = dot product
    → pgvector operator: <=> (cosine distance = 1 - similarity)

    Metadata filtering via JSONB allows restricting search to specific
    documents, file types, or ingestion date ranges.
    """

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            # Model is pre-cached in Docker image — no network call
            self._model = SentenceTransformer(config.embedding_model)
        return self._model

    def _get_connection(self):
        return psycopg2.connect(
            host=config.pg_host,
            dbname=config.pg_db,
            user=config.pg_user,
            password=config.pg_password,
            port=config.pg_port,
            sslmode="require"
        )

    def retrieve(
        self,
        query: str,
        top_k: int = None,
        metadata_filter: dict = None
    ) -> list[dict]:
        top_k = top_k or config.dense_top_k

        # Embed query with same model as ingestion — consistency critical
        query_embedding = self.model.encode(
            query,
            normalize_embeddings=True
        ).tolist()

        # Build optional metadata filter clause
        filter_clause = ""
        filter_params = []
        if metadata_filter:
            # e.g. {"source_blob": "contract.pdf"} → WHERE metadata @> '{"source_blob": "contract.pdf"}'
            import json
            filter_clause = "AND metadata @> %s::jsonb"
            filter_params = [json.dumps(metadata_filter)]

        sql = f"""
            SELECT
                chunk_id,
                text,
                metadata,
                1 - (embedding <=> %s::vector) AS score
            FROM document_chunks
            WHERE 1=1 {filter_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                params = [query_embedding] + filter_params + [query_embedding, top_k]
                cur.execute(sql, params)
                rows = cur.fetchall()
                results = [
                    {
                        "chunk_id": r["chunk_id"],
                        "text":     r["text"],
                        "metadata": r["metadata"],
                        "score":    float(r["score"]),
                        "source":   "dense",
                    }
                    for r in rows
                ]
                logger.info(f"Dense retrieval: {len(results)} chunks for query")
                return results
        finally:
            conn.close()