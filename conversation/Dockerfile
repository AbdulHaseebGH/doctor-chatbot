# --------------------------------------------------------------------------
# Conversation Service Dockerfile
# Phase 3+4 upgrade: includes RAG (sentence-transformers, faiss-cpu)
# Pre-downloads the MiniLM embedding model at build time for fast startup.
# --------------------------------------------------------------------------
FROM python:3.11-slim

# sentence-transformers needs these
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the MiniLM embedding model so container starts instantly
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY app/ .

# Create data directory for scheduler appointments
RUN mkdir -p /app/data

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]