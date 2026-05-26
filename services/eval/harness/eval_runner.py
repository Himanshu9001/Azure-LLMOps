"""
Evaluation runner — orchestrates full eval pipeline.

Flow:
  1. Load golden Q&A dataset from ADLS Gen2
  2. Run RAG API on each question to get answers + contexts
  3. Score with RAGAS (RAG quality)
  4. Score with DeepEval (LLM safety + correctness)
  5. Log all scores to MLflow
  6. Apply eval gate — pass/fail decision
  7. Promote model to Staging if passed

This runs as:
  - Post-training job (after QLoRA fine-tuning)
  - Scheduled job (weekly regression testing)
  - Pre-deploy gate (in GitHub Actions CI/CD)
"""
import json
import logging
import os
import sys
import httpx
import mlflow
import yaml
from datasets import Dataset
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential

from metrics.ragas_evaluator import RAGASEvaluator
from metrics.deepeval_evaluator import DeepEvalEvaluator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_config(path: str = "config/eval_config.yaml") -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    # Override with env vars
    cfg["judge"]["endpoint"]  = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    cfg["mlflow"]["tracking_uri"] = os.environ.get("MLFLOW_TRACKING_URI", "")
    cfg["rag_api"]["endpoint"] = os.environ.get(
        "RAG_API_ENDPOINT",
        "http://rag-api-service.llmops.svc.cluster.local/api/v1"
    )
    return cfg


def load_eval_dataset(cfg: dict) -> list[dict]:
    """
    Load golden Q&A dataset from ADLS Gen2.
    These are human-curated pairs — never used in training.
    """
    credential = DefaultAzureCredential()
    blob_client = BlobServiceClient(
        account_url=f"https://{os.environ['AZURE_STORAGE_ACCOUNT']}.blob.core.windows.net",
        credential=credential
    ).get_blob_client(
        container="eval-datasets",
        blob=cfg["dataset"]["path"]
    )

    content = blob_client.download_blob().readall().decode("utf-8")
    samples = [json.loads(line) for line in content.strip().splitlines()]

    if len(samples) < cfg["dataset"]["min_samples"]:
        raise ValueError(
            f"Eval dataset too small: {len(samples)} < {cfg['dataset']['min_samples']}"
        )

    logger.info(f"Loaded {len(samples)} eval samples")
    return samples


async def run_rag_pipeline(
    samples: list[dict],
    rag_endpoint: str,
    timeout: int = 30
) -> list[dict]:
    """
    Run each question through the RAG API to get answers and contexts.
    Adds 'answer' and 'contexts' fields to each sample.
    """
    results = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i, sample in enumerate(samples):
            try:
                resp = await client.post(
                    f"{rag_endpoint}/query",
                    json={"query": sample["question"]}
                )
                resp.raise_for_status()
                data = resp.json()

                results.append({
                    **sample,
                    "answer":   data["answer"],
                    "contexts": [s["blob"] for s in data.get("sources", [])],
                })

                if i % 10 == 0:
                    logger.info(f"Evaluated {i+1}/{len(samples)} questions")

            except Exception as e:
                logger.warning(f"RAG API failed for question {i}: {e}")
                results.append({
                    **sample,
                    "answer":   "",
                    "contexts": [],
                })

    return results


def run_evaluation(config_path: str = "config/eval_config.yaml") -> bool:
    """
    Main evaluation entry point.
    Returns True if eval gate passes, False if fails.
    """
    cfg = load_config(config_path)
    mlflow.set_tracking_uri(cfg["mlflow"]["tracking_uri"])
    mlflow.set_experiment(cfg["mlflow"]["experiment_name"])

    with mlflow.start_run(run_name="eval-gate"):

        # 1. Load dataset
        samples = load_eval_dataset(cfg)

        # 2. Run RAG pipeline
        import asyncio
        samples_with_answers = asyncio.run(
            run_rag_pipeline(samples, cfg["rag_api"]["endpoint"])
        )

        # 3. Build HuggingFace Dataset for RAGAS
        hf_dataset = Dataset.from_list(samples_with_answers)

        # 4. RAGAS evaluation
        ragas_evaluator = RAGASEvaluator(cfg)
        ragas_scores = ragas_evaluator.evaluate(hf_dataset)
        ragas_passed, ragas_failures = ragas_evaluator.check_thresholds(ragas_scores)

        # 5. DeepEval evaluation
        deepeval_evaluator = DeepEvalEvaluator(cfg)
        deepeval_scores = deepeval_evaluator.evaluate(samples_with_answers)

        # 6. Log all scores to MLflow
        mlflow.log_metrics({
            **{f"ragas_{k}": v for k, v in ragas_scores.items()},
            **{f"deepeval_{k}": v for k, v in deepeval_scores.items()},
        })

        # 7. Eval gate decision
        passed = ragas_passed
        if not passed:
            logger.error(f"Eval gate FAILED: {ragas_failures}")
            mlflow.set_tag("eval_result", "FAILED")
        else:
            logger.info("Eval gate PASSED — model ready for Staging")
            mlflow.set_tag("eval_result", "PASSED")

        return passed


if __name__ == "__main__":
    passed = run_evaluation()
    sys.exit(0 if passed else 1)   # Exit code used by CI/CD gate