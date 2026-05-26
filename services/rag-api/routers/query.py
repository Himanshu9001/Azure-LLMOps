from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import logging

from pipeline.rag_chain import RAGChain

logger  = logging.getLogger(__name__)
router  = APIRouter()
chain   = RAGChain()


class QueryRequest(BaseModel):
    query:           str  = Field(..., min_length=3, max_length=2000)
    metadata_filter: dict = Field(default_factory=dict)
    # Example: {"source_blob": "contract.pdf"} — restrict retrieval to one doc


class SourceCitation(BaseModel):
    blob:         str
    page:         int | str
    rerank_score: float


class QueryResponse(BaseModel):
    answer:  str
    sources: list[SourceCitation]
    cached:  bool
    latency: dict
    debug:   dict


@router.post("/query", response_model=QueryResponse)
async def query_documents(req: QueryRequest):
    """
    Main RAG query endpoint.

    POST /query
    {
      "query": "What is the refund policy?",
      "metadata_filter": {}           # optional — restrict to specific docs
    }
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        result = await chain.run(
            query=req.query,
            metadata_filter=req.metadata_filter or None
        )
        return result
    except Exception as e:
        logger.error(f"RAG pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="RAG pipeline error")


@router.get("/health")
async def health():
    return {"status": "ok"}