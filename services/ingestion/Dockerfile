FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download embedding model at build time
# Avoids cold start delay on first pod execution
RUN python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('sentence-transformers/all-mpnet-base-v2')"

COPY . .

# Non-root user — security best practice
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

CMD ["uvicorn", "ingestion.event_grid_trigger:app", "--host", "0.0.0.0", "--port", "8000"]
