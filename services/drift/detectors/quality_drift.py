"""
Quality drift detection — monitors faithfulness score over time.

Complements embedding drift with output quality monitoring.
A model can start hallucinating without any change in input distribution
— e.g., new document types, model degradation, index corruption.

Detection method:
  Sample 100 random queries per day → run through RAG pipeline
  → score with RAGAS faithfulness → compare vs 7-day rolling average.
  Drop > 5% → alert.
"""
import logging
import random
from datetime import datetime, timedelta
import mlflow
import psycopg2

logger = logging.getLogger(__name__)

class QualityDriftDetector:
    def __init__(self, pg_conn_str: str, mlflow_tracking_uri: str):
        self.pg_conn_str = pg_conn_str
        mlflow.set_tracking_uri(mlflow_tracking_uri)
        self.quality_drop_threshold = 0.05   # 5% drop triggers alert

    def fetch_recent_queries(self, limit: int = 100) -> list[str]:
        """Sample recent queries from query log for quality monitoring."""
        conn = psycopg2.connect(self.pg_conn_str)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT query_text FROM query_logs
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                    ORDER BY random()
                    LIMIT %s
                """, (limit,))
                return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def get_baseline_faithfulness(self, days: int = 7) -> float:
        """Get 7-day rolling average faithfulness from MLflow."""
        client = mlflow.MlflowClient()
        runs = client.search_runs(
            experiment_ids=["llmops-evaluation"],
            filter_string=f"attributes.start_time > {int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)}",
            order_by=["attributes.start_time DESC"],
            max_results=7
        )

        if not runs:
            return 0.85   # Default baseline

        scores = [
            run.data.metrics.get("ragas_faithfulness", 0)
            for run in runs
            if "ragas_faithfulness" in run.data.metrics
        ]
        return sum(scores) / len(scores) if scores else 0.85

    def detect_drift(self, current_faithfulness: float) -> dict:
        """Compare current faithfulness vs baseline."""
        baseline = self.get_baseline_faithfulness()
        drop = baseline - current_faithfulness
        drift_detected = drop > self.quality_drop_threshold

        logger.info(
            f"Quality drift — baseline: {baseline:.3f}, "
            f"current: {current_faithfulness:.3f}, "
            f"drop: {drop:.3f} "
            f"→ {'DRIFT DETECTED' if drift_detected else 'stable'}"
        )

        return {
            "drift_detected":        drift_detected,
            "baseline_faithfulness": baseline,
            "current_faithfulness":  current_faithfulness,
            "drop":                  drop,
            "threshold":             self.quality_drop_threshold,
        }