"""
Retraining trigger — decides when to kick off a new fine-tuning job.

Triggered by:
  1. Embedding drift detected (query distribution shifted)
  2. Quality drift detected (faithfulness dropped)
  3. Scheduled weekly check (regardless of drift)
  4. Manual trigger via API

Actions:
  - Log drift event to MLflow
  - Create Azure ML training job
  - Notify Slack channel
  - Update drift status in PostgreSQL
"""
import logging
import os
from datetime import datetime
from azure.ai.ml import MLClient
from azure.ai.ml import load_job
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

class RetrainingTrigger:
    def __init__(self):
        self.ml_client = MLClient(
            DefaultAzureCredential(),
            subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
            resource_group_name="rg-llmops-prod",
            workspace_name="llmops-ml-workspace",
        )

    def trigger_retraining(self, reason: str, drift_scores: dict) -> str:
        """
        Submit a new Azure ML training job.
        Returns the job name for tracking.
        """
        logger.info(f"Triggering retraining — reason: {reason}")

        job = load_job("training/azure_ml/job.yaml")
        job.display_name = f"auto-retrain-{datetime.utcnow().strftime('%Y%m%d-%H%M')}"
        job.description = f"Auto-triggered: {reason}. Drift scores: {drift_scores}"

        returned_job = self.ml_client.jobs.create_or_update(job)
        logger.info(f"Training job submitted: {returned_job.name}")
        return returned_job.name

    def should_retrain(
        self,
        embedding_drift: dict,
        quality_drift: dict
    ) -> tuple[bool, str]:
        """
        Decision logic for retraining.
        Returns (should_retrain, reason).
        """
        if quality_drift.get("drift_detected") and \
           quality_drift.get("drop", 0) > 0.10:
            return True, "critical_quality_drop"

        if embedding_drift.get("drift_detected") and \
           quality_drift.get("drift_detected"):
            return True, "both_drift_types_detected"

        if embedding_drift.get("drift_score", 0) > 0.25:
            return True, "severe_embedding_drift"

        return False, "no_retraining_needed"