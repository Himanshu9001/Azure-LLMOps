"""
RAGAS evaluation — measures RAG-specific quality metrics.

RAGAS scores four dimensions:
  Faithfulness:      Does the answer contradict the retrieved context?
  Answer Relevancy:  Does the answer address the question?
  Context Precision: Are the retrieved chunks relevant to the question?
  Context Recall:    Were all important chunks retrieved?

Why RAGAS over manual eval?
  RAGAS uses LLM-as-judge — GPT-4 evaluates each answer
  automatically. 500 samples evaluated in minutes, not days.
  Scores correlate strongly with human judgments (r=0.85+).
"""
import logging
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

logger = logging.getLogger(__name__)

class RAGASEvaluator:
    def __init__(self, cfg: dict):
        # GPT-4o-mini as judge — cheaper than GPT-4o, sufficient for eval
        self.llm = LangchainLLMWrapper(AzureChatOpenAI(
            azure_endpoint=cfg["judge"]["endpoint"],
            azure_deployment=cfg["judge"]["deployment"],
            api_version=cfg["judge"]["api_version"],
            temperature=0,
        ))
        self.embeddings = LangchainEmbeddingsWrapper(AzureOpenAIEmbeddings(
            azure_endpoint=cfg["judge"]["endpoint"],
            azure_deployment=cfg["judge"]["embedding_deployment"],
            api_version=cfg["judge"]["api_version"],
        ))
        self.thresholds = cfg["thresholds"]

    def evaluate(self, dataset: Dataset) -> dict:
        """
        Run RAGAS evaluation on a dataset of Q&A pairs.

        Dataset must have columns:
          question:     str
          answer:       str   (model response)
          contexts:     list[str]  (retrieved chunks)
          ground_truth: str   (expected answer)
        """
        logger.info(f"Running RAGAS on {len(dataset)} samples...")

        results = evaluate(
            dataset=dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
            llm=self.llm,
            embeddings=self.embeddings,
        )

        scores = results.to_pandas().mean().to_dict()
        logger.info(f"RAGAS scores: {scores}")
        return scores

    def check_thresholds(self, scores: dict) -> tuple[bool, list[str]]:
        """
        Check if all scores meet promotion thresholds.
        Returns (passed, list_of_failures).
        """
        failures = []
        for metric, threshold in self.thresholds.items():
            score = scores.get(metric, 0)
            if score < threshold:
                failures.append(
                    f"{metric}: {score:.3f} < {threshold} (FAIL)"
                )
            else:
                logger.info(f"{metric}: {score:.3f} >= {threshold} (PASS)")

        return len(failures) == 0, failures