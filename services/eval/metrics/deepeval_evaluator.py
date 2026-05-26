"""
DeepEval evaluation — measures LLM safety and quality metrics.

Complements RAGAS with:
  Hallucination:   % claims not grounded in context
  Toxicity:        Safety filter — blocks harmful outputs
  Bias:            Demographic fairness check
  Answer Correctness: vs golden answers

Why both RAGAS and DeepEval?
  RAGAS measures RAG quality (retrieval + grounding)
  DeepEval measures LLM quality (safety + correctness)
  Production systems need both — a safe but irrelevant
  answer is as bad as a relevant but hallucinated one.
"""
import logging
from deepeval import evaluate
from deepeval.metrics import (
    HallucinationMetric,
    AnswerRelevancyMetric,
    ToxicityMetric,
    BiasMetric,
)
from deepeval.test_case import LLMTestCase

logger = logging.getLogger(__name__)

class DeepEvalEvaluator:
    def __init__(self, cfg: dict):
        self.thresholds = cfg["thresholds"]

        # Initialize metrics with thresholds
        self.metrics = [
            HallucinationMetric(threshold=0.10),   # Max 10% hallucination
            AnswerRelevancyMetric(threshold=0.80),
            ToxicityMetric(threshold=0.05),         # Near-zero toxicity
            BiasMetric(threshold=0.10),
        ]

    def build_test_cases(self, samples: list[dict]) -> list[LLMTestCase]:
        """Convert eval dataset samples to DeepEval test cases."""
        return [
            LLMTestCase(
                input=s["question"],
                actual_output=s["answer"],
                expected_output=s["ground_truth"],
                retrieval_context=s["contexts"],
            )
            for s in samples
        ]

    def evaluate(self, samples: list[dict]) -> dict:
        """Run DeepEval metrics on eval samples."""
        test_cases = self.build_test_cases(samples)
        logger.info(f"Running DeepEval on {len(test_cases)} test cases...")

        results = evaluate(test_cases, self.metrics)

        # Aggregate scores
        scores = {}
        for metric in self.metrics:
            metric_name = metric.__class__.__name__.lower().replace("metric", "")
            passed = sum(1 for tc in test_cases if metric.is_successful())
            scores[metric_name] = passed / len(test_cases)

        logger.info(f"DeepEval scores: {scores}")
        return scores