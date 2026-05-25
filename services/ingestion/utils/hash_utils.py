import hashlib

def compute_document_hash(content: bytes) -> str:
    """
    SHA256 hash of raw document bytes.
    Used for idempotency — skip re-embedding unchanged documents.
    Same document uploaded twice produces same hash → no duplicate embeddings.
    """
    return hashlib.sha256(content).hexdigest()

def compute_chunk_id(doc_hash: str, chunk_index: int) -> str:
    """
    Deterministic chunk ID from document hash + position.
    Same document + same chunk index always = same ID.
    Enables safe upsert into pgvector — pipeline is fully idempotent.
    """
    return hashlib.md5(f"{doc_hash}:{chunk_index}".encode()).hexdigest()
