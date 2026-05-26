"""
Embedding drift detection using Evidently AI.

Detects when the distribution of user queries shifts significantly
from the baseline — signals domain shift or new use patterns.

Why detect embedding drift?
  If users start asking questions your RAG pipeline wasn't designed for,
  retrieval quality drops silently. Faithfulness scores look fine
  (because the LLM faithfully answers from context) but the context
  is wrong for the new query types.

Detection method:
  Jensen-Shannon divergence between baseline and current query embeddings.
  JS divergence > 0.15 → alert → trigger human review.
"""
import logging
import numpy as np
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from evidently.metrics import EmbeddingsDriftMetric
from evidently.report import Report
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class EmbeddingDriftDetector:
    def __init__(self, pg_conn_str: str, model_name: str = "sentence-transformers/all-mpnet-base-v2"):
        self.pg_conn_str = pg_conn_str
        self.model = SentenceTransformer(model_name)
        self.drift_threshold = 0.15   # JS divergence threshold

    def fetch_query_embeddings(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 1000
    ) -> np.ndarray:
        """
        Fetch query embeddings from query log table.
        Assumes queries are logged to PostgreSQL by RAG API.
        """
        conn = psycopg2.connect(self.pg_conn_str)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT query_text FROM query_logs
                    WHERE created_at BETWEEN %s AND %s
                    ORDER BY random()
                    LIMIT %s
                """, (start_date, end_date, limit))
                queries = [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

        if not queries:
            return np.array([])

        return self.model.encode(queries, normalize_embeddings=True)

    def detect_drift(
        self,
        baseline_days: int = 7,
        current_days: int = 1
    ) -> dict:
        """
        Compare current query distribution vs baseline.

        baseline: embeddings from 7-14 days ago (stable reference)
        current:  embeddings from last 24 hours
        """
        now = datetime.utcnow()

        baseline_embeddings = self.fetch_query_embeddings(
            start_date=now - timedelta(days=baseline_days + 7),
            end_date=now - timedelta(days=baseline_days),
        )

        current_embeddings = self.fetch_query_embeddings(
            start_date=now - timedelta(days=current_days),
            end_date=now,
        )

        if len(baseline_embeddings) == 0 or len(current_embeddings) == 0:
            logger.warning("Insufficient data for drift detection")
            return {"drift_detected": False, "reason": "insufficient_data"}

        # Evidently drift report
        report = Report(metrics=[EmbeddingsDriftMetric()])
        report.run(
            reference_data=baseline_embeddings,
            current_data=current_embeddings,
        )

        result = report.as_dict()
        drift_score = result["metrics"][0]["result"]["drift_score"]
        drift_detected = drift_score > self.drift_threshold

        logger.info(
            f"Embedding drift score: {drift_score:.4f} "
            f"(threshold: {self.drift_threshold}) "
            f"→ {'DRIFT DETECTED' if drift_detected else 'no drift'}"
        )

        return {
            "drift_detected":  drift_detected,
            "drift_score":     drift_score,
            "threshold":       self.drift_threshold,
            "baseline_samples": len(baseline_embeddings),
            "current_samples":  len(current_embeddings),
        }