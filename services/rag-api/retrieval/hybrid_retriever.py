import logging
from retrieval.dense_retriever import DenseRetriever
from retrieval.sparse_retriever import SparseRetriever

logger = logging.getLogger(__name__)

class HybridRetriever:
    """
    Reciprocal Rank Fusion (RRF) of dense + sparse results.

    RRF formula per chunk:
        score = Σ 1 / (k + rank_i)   where k=60 (smoothing constant)

    Why RRF over weighted sum?
      - Score scales differ wildly: dense scores are [0,1] cosine similarity,
        BM25 scores are [0,~3] tf-idf based — not directly comparable.
      - RRF operates on ranks, not raw scores — no calibration needed.
      - Empirically outperforms simple score fusion on BEIR benchmark.
      - k=60 is the standard constant from the original RRF paper (Cormack 2009).

    Result: chunks that appear high in BOTH lists get boosted strongly.
    Chunks that appear in only one list still get partial credit.
    """

    def __init__(self):
        self.dense  = DenseRetriever()
        self.sparse = SparseRetriever()

    def retrieve(
        self,
        query: str,
        dense_top_k:  int = 20,
        sparse_top_k: int = 20,
        rrf_k:        int = 60,
    ) -> list[dict]:
        # Run both retrievers
        dense_results  = self.dense.retrieve(query, top_k=dense_top_k)
        sparse_results = self.sparse.retrieve(query, top_k=sparse_top_k)

        # Build rank maps: chunk_id → rank (1-indexed)
        dense_ranks  = {r["chunk_id"]: i + 1 for i, r in enumerate(dense_results)}
        sparse_ranks = {r["chunk_id"]: i + 1 for i, r in enumerate(sparse_results)}

        # Collect all unique chunk_ids from both retrievers
        all_chunk_ids = set(dense_ranks) | set(sparse_ranks)

        # Build combined chunk lookup
        chunk_map = {r["chunk_id"]: r for r in dense_results}
        chunk_map.update({r["chunk_id"]: r for r in sparse_results})

        # RRF scoring
        rrf_scores = {}
        for chunk_id in all_chunk_ids:
            score = 0.0
            if chunk_id in dense_ranks:
                score += 1.0 / (rrf_k + dense_ranks[chunk_id])
            if chunk_id in sparse_ranks:
                score += 1.0 / (rrf_k + sparse_ranks[chunk_id])
            rrf_scores[chunk_id] = score

        # Sort by RRF score descending
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for chunk_id, rrf_score in ranked:
            chunk = chunk_map[chunk_id].copy()
            chunk["rrf_score"] = rrf_score
            results.append(chunk)

        logger.info(
            f"Hybrid retrieval: {len(dense_results)} dense + "
            f"{len(sparse_results)} sparse → {len(results)} unique chunks"
        )
        return results