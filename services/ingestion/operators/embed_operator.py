import logging
from airflow.models import BaseOperator
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class EmbedOperator(BaseOperator):
    """
    Stage 3 — Generate embeddings for all chunks in batches.

    Model: all-mpnet-base-v2
      - 768-dim dense vectors
      - Strong semantic similarity on English text
      - Apache 2.0 license — production safe

    normalize_embeddings=True → L2 normalize so cosine similarity = dot product.
    Batching prevents OOM on large documents.
    Runs on CPU node pool — GPU reserved for vLLM and fine-tuning.
    """

    def __init__(
        self,
        model_name:  str = "sentence-transformers/all-mpnet-base-v2",
        batch_size:  int = 32,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.model_name = model_name
        self.batch_size = batch_size

    def execute(self, context: dict) -> dict:
        ti       = context["ti"]
        chunking = ti.xcom_pull(task_ids="chunk_document")
        chunks   = chunking["chunks"]
        doc_hash = chunking["doc_hash"]

        if not chunks:
            logger.warning("No chunks to embed")
            return {"embedded_chunks": [], "doc_hash": doc_hash}

        # Model cached in pod after first load — no cold start on subsequent runs
        model = SentenceTransformer(self.model_name)
        texts = [c["text"] for c in chunks]
        all_embeddings = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i: i + self.batch_size]
            embeddings = model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            all_embeddings.extend(embeddings.tolist())
            logger.info(f"Embedded batch {i // self.batch_size + 1} ({len(batch)} chunks)")

        embedded_chunks = [
            {**chunk, "embedding": emb}
            for chunk, emb in zip(chunks, all_embeddings)
        ]

        logger.info(f"Embedded {len(embedded_chunks)} chunks total")
        return {"embedded_chunks": embedded_chunks, "doc_hash": doc_hash}
