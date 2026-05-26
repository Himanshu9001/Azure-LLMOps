import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a document Q&A assistant. Your job is to answer questions strictly based on the provided context from internal documents.

Rules:
- Answer ONLY from the context below. Do not use any external knowledge.
- If the answer is not in the context, say exactly: "I don't have enough information in the provided documents to answer this question."
- Always cite the source document for every factual claim using the format: [Source: <filename>]
- Be precise and concise. Do not pad your answer.
- If multiple documents contain relevant information, synthesize them coherently."""

def build_prompt(query: str, chunks: list[dict]) -> tuple[str, list[dict]]:
    """
    Assemble retrieved chunks into a structured prompt context.

    Returns the formatted prompt AND the sources list for the API response.
    Sources are included in the response so the caller can render citations.

    Context format:
      Each chunk is numbered and labeled with its source document.
      Numbering helps the model reference specific context blocks.
    """
    if not chunks:
        context = "No relevant context found in the document store."
        sources = []
    else:
        context_parts = []
        sources = []
        for i, chunk in enumerate(chunks, 1):
            source_blob = chunk.get("metadata", {}).get("source_blob", "unknown")
            page_num    = chunk.get("metadata", {}).get("page_number", "?")
            context_parts.append(
                f"[{i}] Source: {source_blob} (page {page_num})\n{chunk['text']}"
            )
            if source_blob not in [s["blob"] for s in sources]:
                sources.append({
                    "blob":         source_blob,
                    "page":         page_num,
                    "rerank_score": chunk.get("rerank_score", 0.0),
                })

        context = "\n\n".join(context_parts)

    user_prompt = f"""Context:
{context}

Question: {query}

Answer:"""

    return SYSTEM_PROMPT, user_prompt, sources