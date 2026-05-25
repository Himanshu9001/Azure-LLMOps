import logging
from airflow.models import BaseOperator
from langchain.text_splitter import RecursiveCharacterTextSplitter
from ingestion.utils.text_cleaner import clean_extracted_text, is_valid_chunk
from ingestion.utils.hash_utils import compute_chunk_id
from ingestion.utils.metadata import build_chunk_metadata

logger = logging.getLogger(__name__)

class ChunkOperator(BaseOperator):
    """
    Stage 2 — Clean extracted text and split into overlapping chunks.

    RecursiveCharacterTextSplitter splits on paragraph → sentence → word.
    Tries largest separator first — preserves semantic boundaries.
    chunk_overlap=64 prevents context loss at chunk boundaries.
    """

    def __init__(
        self,
        chunk_size:     int = 512,
        chunk_overlap:  int = 64,
        min_chunk_size: int = 50,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.chunk_size     = chunk_size
        self.chunk_overlap  = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def execute(self, context: dict) -> dict:
        ti             = context["ti"]
        extraction     = ti.xcom_pull(task_ids="extract_document")
        blob_name      = extraction["blob_name"]
        doc_hash       = extraction["doc_hash"]
        pages          = extraction["pages"]
        page_count     = extraction["page_count"]

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

        chunks      = []
        chunk_index = 0

        for page in pages:
            cleaned = clean_extracted_text(page["text"])
            if not cleaned:
                continue

            for chunk_text in splitter.split_text(cleaned):
                if not is_valid_chunk(chunk_text, self.min_chunk_size):
                    continue

                chunks.append({
                    "chunk_id": compute_chunk_id(doc_hash, chunk_index),
                    "text":     chunk_text,
                    "metadata": build_chunk_metadata(
                        blob_name=blob_name,
                        doc_hash=doc_hash,
                        page_count=page_count,
                        page_number=page["page_number"],
                        chunk_index=chunk_index,
                    )
                })
                chunk_index += 1

        logger.info(f"Produced {len(chunks)} chunks from {page_count} pages")
        return {"chunks": chunks, "doc_hash": doc_hash}
