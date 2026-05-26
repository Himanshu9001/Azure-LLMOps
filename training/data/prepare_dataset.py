import json
import hashlib
import logging
import psycopg2
import psycopg2.extras
from openai import AzureOpenAI
from pathlib import Path

logger = logging.getLogger(__name__)

# Alpaca-style instruction format — what SFTTrainer expects
SYSTEM_PROMPT = """You are a document Q&A assistant. Answer questions strictly 
from the provided context. Always cite the source document."""

QA_GENERATION_PROMPT = """You are generating training data for a document Q&A system.

Given the following document chunk, generate {num_pairs} question-answer pairs.
Requirements:
- Questions must be answerable ONLY from this chunk
- Answers must be grounded — no external knowledge
- Include the source citation in every answer
- Vary question types: factual, inferential, definitional
- Return as JSON array: [{{"question": "...", "answer": "..."}}]

Document chunk:
{chunk_text}

Source: {source_blob}"""

def format_training_sample(question: str, answer: str, context: str) -> dict:
    """
    Format a Q&A pair into Mistral instruct format.
    
    Mistral instruct template:
    <s>[INST] {instruction} [/INST] {response}</s>
    
    We include context in the instruction so the model learns
    to ground answers in provided context — not memorize facts.
    """
    instruction = f"""Context:
{context}

Question: {question}"""

    return {
        "text": f"<s>[INST] {instruction} [/INST] {answer}</s>"
    }

def fetch_chunks_from_pgvector(pg_conn_str: str, limit: int = 1000) -> list[dict]:
    """Pull chunks from vectorstore — these are your training data source."""
    conn = psycopg2.connect(pg_conn_str)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT chunk_id, text, metadata
                FROM document_chunks
                WHERE length(text) > 200    -- Skip very short chunks
                ORDER BY random()
                LIMIT %s
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def generate_qa_pairs(
    chunks: list[dict],
    openai_client: AzureOpenAI,
    pairs_per_chunk: int = 3,
    output_path: str = "training/data/train.jsonl"
) -> None:
    """
    Generate synthetic Q&A pairs from document chunks using GPT-4.
    
    Why synthetic data?
      Real human-annotated Q&A pairs are expensive and slow.
      GPT-4 generated pairs are 80% as good for instruction tuning.
      Use synthetic data to bootstrap, then replace with human data over time.
    """
    samples = []
    failed = 0

    for i, chunk in enumerate(chunks):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": QA_GENERATION_PROMPT.format(
                        num_pairs=pairs_per_chunk,
                        chunk_text=chunk["text"],
                        source_blob=chunk["metadata"].get("source_blob", "unknown")
                    )
                }],
                temperature=0.7,
                response_format={"type": "json_object"}
            )

            pairs = json.loads(response.choices[0].message.content)
            if isinstance(pairs, dict):
                pairs = pairs.get("pairs", pairs.get("questions", []))

            for pair in pairs:
                sample = format_training_sample(
                    question=pair["question"],
                    answer=pair["answer"],
                    context=chunk["text"]
                )
                samples.append(sample)

            if i % 50 == 0:
                logger.info(f"Generated {len(samples)} samples from {i+1}/{len(chunks)} chunks")

        except Exception as e:
            logger.warning(f"Failed chunk {chunk['chunk_id'][:8]}: {e}")
            failed += 1

    # Write JSONL — one sample per line
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")

    logger.info(
        f"Dataset complete: {len(samples)} samples, "
        f"{failed} failed chunks, saved to {output_path}"
    )