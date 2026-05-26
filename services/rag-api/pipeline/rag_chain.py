import logging
import time
import httpx

from config.settings import config
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.reranker import Reranker
from pipeline.prompt_builder import build_prompt
from cache.redis_cache import cache

logger = logging.getLogger(__name__)

class RAGChain:
    """
    Orchestrates the full RAG pipeline end-to-end.

    Flow:
      1. Cache check (Redis)
      2. Hybrid retrieval (dense + sparse → RRF fusion)
      3. Cross-encoder reranking
      4. Prompt assembly
      5. vLLM inference (OpenAI-compatible API)
      6. Cache write + return

    vLLM exposes an OpenAI-compatible /v1/chat/completions endpoint.
    No LangChain dependency for the LLM call — direct HTTP is simpler,
    observable, and doesn't hide latency behind abstraction layers.
    """

    def __init__(self):
        self.retriever = HybridRetriever()
        self.reranker  = Reranker()

    async def run(self, query: str, metadata_filter: dict = None) -> dict:
        t_start = time.monotonic()

        # 1. Cache check
        cached = cache.get(query)
        if cached:
            cached["cached"] = True
            return cached

        # 2. Hybrid retrieval
        t0 = time.monotonic()
        candidates = self.retriever.retrieve(
            query,
            dense_top_k=config.dense_top_k,
            sparse_top_k=config.sparse_top_k,
        )
        retrieval_ms = int((time.monotonic() - t0) * 1000)

        # 3. Reranking
        t0 = time.monotonic()
        top_chunks = self.reranker.rerank(
            query,
            candidates,
            top_k=config.rerank_top_k
        )
        rerank_ms = int((time.monotonic() - t0) * 1000)

        # 4. Prompt assembly
        system_prompt, user_prompt, sources = build_prompt(query, top_chunks)

        # 5. vLLM inference (OpenAI-compatible)
        t0 = time.monotonic()
        answer = await self._call_vllm(system_prompt, user_prompt)
        llm_ms = int((time.monotonic() - t0) * 1000)

        total_ms = int((time.monotonic() - t_start) * 1000)

        response = {
            "answer":  answer,
            "sources": sources,
            "cached":  False,
            "latency": {
                "retrieval_ms": retrieval_ms,
                "rerank_ms":    rerank_ms,
                "llm_ms":       llm_ms,
                "total_ms":     total_ms,
            },
            "debug": {
                "candidates_retrieved": len(candidates),
                "chunks_after_rerank":  len(top_chunks),
                "top_chunk_score":      top_chunks[0].get("rerank_score", 0) if top_chunks else 0,
            }
        }

        # 6. Cache write
        cache.set(query, response)

        return response

    async def _call_vllm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call vLLM's OpenAI-compatible chat completions endpoint.
        Phase 4 will deploy vLLM — this stub falls back gracefully.
        """
        payload = {
            "model":       config.llm_model,
            "messages": [
                {"role": "system",  "content": system_prompt},
                {"role": "user",    "content": user_prompt},
            ],
            "max_tokens":  config.llm_max_tokens,
            "temperature": config.llm_temperature,
            "stream":      False,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{config.vllm_endpoint}/chat/completions",
                    json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]

        except httpx.ConnectError:
            # Phase 4 not yet deployed — return retrieval result with note
            logger.warning("vLLM endpoint not reachable — returning context only (Phase 4 pending)")
            return (
                "[vLLM not yet deployed — Phase 4 pending]\n\n"
                "Retrieved context is ready. Deploy vLLM in Phase 4 to complete the pipeline."
            )
        except Exception as e:
            logger.error(f"vLLM call failed: {e}")
            raise