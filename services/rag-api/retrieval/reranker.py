import logging
from sentence_transformers import CrossEncoder

from config.settings import config

logger = logging.getLogger(__name__)

class Reranker:
    """
    Cross-encoder reranker — ms-marco-MiniLM-L-6-v2.

    Why reranking?
      ANN search (HNSW) is approximate — it can miss relevant chunks and
      return marginally relevant ones. A cross-encoder scores query+chunk
      TOGETHER (not independently), capturing deep interaction signals.

    Architecture difference:
      Bi-encoder (embedding model): encodes query and chunk separately.
        Fast but loses query-chunk interaction signal.
      Cross-encoder: concatenates [query, chunk] → single forward pass.
        Slow for retrieval (can't pre-compute), but precise for re-scoring.

    MiniLM-L-6-v2 has 22M params — scores 20 chunks in ~50ms on CPU.
    Use it to go from top-20 (hybrid) → top-5 (final context).

    Scores are logits — not calibrated probabilities. Only ranking matters.
    """

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = CrossEncoder(config.reranker_model)
        return self._model

    def rerank(self, query: str, chunks: list[dict], top_k: int = None) -> list[dict]:
        top_k = top_k or config.rerank_top_k

        if not chunks:
            return []

        if len(chunks) <= top_k:
            # No reranking needed — return as-is
            return chunks[:top_k]

        # Create query-chunk pairs for cross-encoder
        pairs = [(query, chunk["text"]) for chunk in chunks]
        scores = self.model.predict(pairs)

        # Attach reranker score to each chunk
        for chunk, score in zip(chunks, scores):
            chunk["rerank_score"] = float(score)

        # Sort by reranker score and return top_k
        reranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
        top_chunks = reranked[:top_k]

        logger.info(
            f"Reranker: {len(chunks)} → {len(top_chunks)} chunks "
            f"(top score: {top_chunks[0]['rerank_score']:.3f})"
        )
        return top_chunks