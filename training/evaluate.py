"""
Post-training evaluation gate.

Runs RAGAS metrics on the fine-tuned model before promoting
to MLflow "Staging". If any metric fails threshold, model
stays in "None" stage and CI/CD pipeline is blocked.
"""
import os
import json
import logging
import mlflow
from mlflow import MlflowClient
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from ragas.llms import LangchainLLMWrapper
from langchain_openai import AzureChatOpenAI
from langchain_openai import AzureOpenAIEmbeddings

logger = logging.getLogger(__name__)

# Promotion thresholds — model must pass ALL to reach Staging
THRESHOLDS = {
    "faithfulness":      0.85,   # Answer grounded in context
    "answer_relevancy":  0.80,   # Answer addresses the question
    "context_precision": 0.75,   # Retrieved chunks are relevant
    "context_recall":    0.70,   # Important chunks were retrieved
}

def load_eval_dataset(eval_path: str) -> Dataset:
    """
    Golden Q&A dataset — human-curated, never used in training.

    Format (JSONL):
    {
      "question": "What is the refund policy?",
      "answer": "Refunds are issued within 30 days per Section 4.2",
      "contexts": ["Section 4.2 states refunds..."],
      "ground_truth": "Refunds are issued within 30 days"
    }
    """
    samples = []
    with open(eval_path) as f:
        for line in f:
            samples.append(json.loads(line.strip()))

    return Dataset.from_list(samples)

def run_model_inference(
    model,
    tokenizer,
    dataset: Dataset,
    max_new_tokens: int = 512
) -> Dataset:
    """
    Run fine-tuned model on eval questions to get answers.
    These answers are then scored by RAGAS.
    """
    answers = []

    for sample in dataset:
        context = "\n".join(sample["contexts"])
        prompt = f"""<s>[INST] Context:
{context}

Question: {sample['question']} [/INST]"""

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.1,
                do_sample=False,         # Greedy decoding for eval consistency
            )
        answer = tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )
        answers.append(answer.strip())

    return dataset.add_column("answer", answers)

def evaluate_model(
    model,
    tokenizer,
    eval_path: str,
    mlflow_run_id: str,
    model_version: str,
) -> bool:
    """
    Full evaluation pipeline.
    Returns True if model passes all thresholds → safe to promote.
    Returns False if any metric fails → block promotion.
    """
    mlflow_client = MlflowClient()

    # Load golden eval dataset
    eval_dataset = load_eval_dataset(eval_path)
    logger.info(f"Loaded {len(eval_dataset)} eval samples")

    # Run model inference
    eval_dataset = run_model_inference(model, tokenizer, eval_dataset)

    # Setup RAGAS with Azure OpenAI as judge
    judge_llm = LangchainLLMWrapper(AzureChatOpenAI(
        azure_deployment="gpt-4o",
        api_version="2024-02-01",
    ))
    judge_embeddings = AzureOpenAIEmbeddings(
        azure_deployment="text-embedding-3-small",
    )

    # Run RAGAS evaluation
    logger.info("Running RAGAS evaluation...")
    results = evaluate(
        dataset=eval_dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        llm=judge_llm,
        embeddings=judge_embeddings,
    )

    scores = results.to_pandas().mean().to_dict()
    logger.info(f"Evaluation scores: {scores}")

    # Log scores to MLflow
    with mlflow.start_run(run_id=mlflow_run_id):
        mlflow.log_metrics({
            "eval_faithfulness":      scores.get("faithfulness", 0),
            "eval_answer_relevancy":  scores.get("answer_relevancy", 0),
            "eval_context_precision": scores.get("context_precision", 0),
            "eval_context_recall":    scores.get("context_recall", 0),
        })

    # Eval gate — check all thresholds
    passed = True
    for metric, threshold in THRESHOLDS.items():
        score = scores.get(metric, 0)
        status = "✅ PASS" if score >= threshold else "❌ FAIL"
        logger.info(f"{status} {metric}: {score:.3f} (threshold: {threshold})")
        if score < threshold:
            passed = False

    # Promote or reject model in MLflow registry
    if passed:
        mlflow_client.transition_model_version_stage(
            name="mistral-7b-docqa",
            version=model_version,
            stage="Staging",
            archive_existing_versions=False,
        )
        logger.info(f"Model v{model_version} promoted to Staging")
    else:
        logger.warning(
            f"Model v{model_version} FAILED eval gate — "
            f"staying in None stage. Fix training data or hyperparameters."
        )

    return passed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path",    required=True)
    parser.add_argument("--eval-path",     required=True)
    parser.add_argument("--mlflow-run-id", required=True)
    parser.add_argument("--model-version", required=True)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model_path)

    passed = evaluate_model(
        model=model,
        tokenizer=tokenizer,
        eval_path=args.eval_path,
        mlflow_run_id=args.mlflow_run_id,
        model_version=args.model_version,
    )

    exit(0 if passed else 1)   # Exit code used by CI/CD gate