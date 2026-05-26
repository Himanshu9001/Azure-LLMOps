import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from routers.query import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up models at startup — avoids cold start on first request
    logger.info("Warming up embedding model and reranker...")
    from retrieval.dense_retriever import DenseRetriever
    from retrieval.reranker import Reranker
    DenseRetriever().model        # loads all-mpnet-base-v2
    Reranker().model              # loads cross-encoder
    logger.info("Models ready.")
    yield


app = FastAPI(
    title="LLMOps RAG API",
    version="1.0.0",
    description="Hybrid retrieval RAG pipeline — Document Q&A on Azure",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in Phase 10 (security hardening)
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request latency logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    t = time.monotonic()
    response = await call_next(request)
    ms = int((time.monotonic() - t) * 1000)
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({ms}ms)")
    return response

app.include_router(router, prefix="/api/v1")