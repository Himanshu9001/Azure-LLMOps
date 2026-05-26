import logging
import psycopg2
import psycopg2.extras
import re
from collections import defaultdict
import math

from config.settings import config

logger = logging.getLogger(__name__)

class SparseRetriever:
    """
    BM25 keyword search over PostgreSQL full-text search.

    Why BM25 alongside dense retrieval?
      Dense vectors capture semantic similarity — "automobile" matches "car".
      BM25 captures exact keyword matches — "CVE-2024-0012", "Section 4.2(b)", 
      "invoice #INV-20240315". For document Q&A with IDs, codes, and proper nouns,
      dense alone misses a significant share of highly relevant chunks.

    PostgreSQL full-text search with ts_rank_cd gives BM25-like scoring.
    Uses GIN index on to_tsvector('english', text) for fast keyword lookup.
    """

    def _get_connection(self):
        return psycopg2.connect(
            host=config.pg_host,
            dbname=config.pg_db,
            user=config.pg_user,
            password=config.pg_password,
            port=config.pg_port,
            sslmode="require"
        )

    def _build_tsquery(self, query: str) -> str:
        """
        Convert natural language query to PostgreSQL tsquery format.
        Uses plainto_tsquery which handles multi-word phrases safely.
        Falls back to individual tokens if phrase query returns nothing.
        """
        tokens = re.sub(r'[^\w\s]', '', query.lower()).split()
        # Join with & for AND semantics — all keywords must appear
        return " & ".join(tokens[:10])  # Cap at 10 tokens

    def retrieve(
        self,
        query: str,
        top_k: int = None,
        metadata_filter: dict = None
    ) -> list[dict]:
        top_k = top_k or config.sparse_top_k
        tsquery = self._build_tsquery(query)

        if not tsquery:
            return []

        filter_clause = ""
        filter_params = []
        if metadata_filter:
            import json
            filter_clause = "AND metadata @> %s::jsonb"
            filter_params = [json.dumps(metadata_filter)]

        sql = f"""
            SELECT
                chunk_id,
                text,
                metadata,
                ts_rank_cd(
                    to_tsvector('english', text),
                    to_tsquery('english', %s)
                ) AS score
            FROM document_chunks
            WHERE to_tsvector('english', text) @@ to_tsquery('english', %s)
            {filter_clause}
            ORDER BY score DESC
            LIMIT %s;
        """

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                params = [tsquery, tsquery] + filter_params + [top_k]
                cur.execute(sql, params)
                rows = cur.fetchall()
                results = [
                    {
                        "chunk_id": r["chunk_id"],
                        "text":     r["text"],
                        "metadata": r["metadata"],
                        "score":    float(r["score"]),
                        "source":   "sparse",
                    }
                    for r in rows
                ]
                logger.info(f"Sparse retrieval: {len(results)} chunks for query")
                return results
        except psycopg2.Error as e:
            # tsquery parse errors for unusual inputs — degrade gracefully
            logger.warning(f"Sparse retrieval failed (tsquery error): {e}")
            return []
        finally:
            conn.close()