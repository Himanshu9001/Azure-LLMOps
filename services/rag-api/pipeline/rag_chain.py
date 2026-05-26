import os
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
      5. LLM Router — tries vLLM first, falls back to Azure OpenAI
      6. Cache write + return

    Langfuse tracing will be added in Phase 8 once the
    Langfuse server is deployed and the correct package
    version is confirmed.
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

        # 5. LLM Router — vLLM primary, Azure OpenAI fallback
        t0 = time.monotonic()
        answer, llm_backend = await self._call_llm_router(system_prompt, user_prompt)
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
                "llm_backend":          llm_backend,
            }
        }

        # 6. Cache write
        cache.set(query, response)

        return response

    async def _call_llm_router(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> tuple[str, str]:
        """
        LLM Router — tries backends in priority order.

        Routing logic:
          1. vLLM enabled + healthy + queue < threshold → use vLLM
          2. Azure OpenAI enabled → fallback
          3. Both disabled → return stub (dev mode only)
        """
        # Try vLLM first if configured
        if config.vllm_enabled:
            vllm_healthy, queue_depth = await self._check_vllm_health()

            if vllm_healthy and queue_depth < config.vllm_queue_threshold:
                try:
                    answer = await self._call_vllm(system_prompt, user_prompt)
                    logger.info(f"vLLM served request (queue_depth={queue_depth})")
                    return answer, "vllm"
                except Exception as e:
                    logger.warning(f"vLLM failed: {e} — falling back to Azure OpenAI")
            else:
                logger.info(
                    f"vLLM skipped — healthy={vllm_healthy}, "
                    f"queue={queue_depth}/{config.vllm_queue_threshold}"
                )

        # Fall back to Azure OpenAI
        if config.azure_openai_enabled:
            try:
                answer = await self._call_azure_openai(system_prompt, user_prompt)
                logger.info("Azure OpenAI served request")
                return answer, "azure_openai"
            except Exception as e:
                logger.error(f"Azure OpenAI failed: {e}")
                raise

        # Both disabled — stub response
        logger.warning("No LLM backend enabled — returning stub")
        return (
            "[No LLM backend configured]\n\n"
            "Set VLLM_ENABLED=true or AZURE_OPENAI_ENABLED=true.",
            "stub"
        )

    async def _check_vllm_health(self) -> tuple[bool, int]:
        """Check vLLM health and queue depth. Timeout=2s."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                health = await client.get(f"{config.vllm_endpoint}/health")
                if health.status_code != 200:
                    return False, 0

                metrics = await client.get(
                    config.vllm_endpoint.replace("/v1", "") + "/metrics"
                )
                queue_depth = 0
                for line in metrics.text.splitlines():
                    if line.startswith("vllm_num_requests_waiting"):
                        queue_depth = int(float(line.split()[-1]))
                        break

                return True, queue_depth

        except Exception:
            return False, 0

    async def _call_vllm(self, system_prompt: str, user_prompt: str) -> str:
        """Call vLLM OpenAI-compatible endpoint."""
        payload = {
            "model":       config.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "max_tokens":  config.llm_max_tokens,
            "temperature": config.llm_temperature,
            "stream":      False,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{config.vllm_endpoint}/chat/completions",
                json=payload
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def _call_azure_openai(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call Azure OpenAI endpoint.
        Uses api-key header — not Bearer token.
        Uses deployment name — not model name.
        API version must match the deployed model.
        """
        payload = {
            "model": config.azure_openai_deployment,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "max_tokens":  config.llm_max_tokens,
            "temperature": config.llm_temperature,
            "stream":      False,
        }

        url = (
            f"{config.azure_openai_endpoint}/openai/deployments/"
            f"{config.azure_openai_deployment}/chat/completions"
            f"?api-version={config.azure_openai_api_version}"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"api-key": config.azure_openai_key}
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]