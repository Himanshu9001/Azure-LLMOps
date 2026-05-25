import os
from datetime import datetime

def build_chunk_metadata(
    blob_name:  str,
    doc_hash:   str,
    page_count: int,
    page_number: int,
    chunk_index: int,
) -> dict:
    """
    Metadata attached to every chunk stored in pgvector.
    Enables filtered retrieval — query only specific docs,
    date ranges, file types, or pipeline versions.
    """
    return {
        "source_blob":      blob_name,
        "file_type":        os.path.splitext(blob_name)[1].lower().lstrip('.'),
        "doc_hash":         doc_hash,
        "page_count":       page_count,
        "page_number":      page_number,
        "chunk_index":      chunk_index,
        "ingested_at":      datetime.utcnow().isoformat(),
        "pipeline_version": "2.0.0",
    }
