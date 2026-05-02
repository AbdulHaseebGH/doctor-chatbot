# --------------------------------------------------------------------------
# conversation/app/rag/vector_store.py
#
# FAISS-backed vector store for clinic documents.
# Builds the index lazily from the documents/ folder.
# --------------------------------------------------------------------------

import os
import glob
import faiss
import numpy as np
from .embedder import embed

_index = None          # FAISS index
_chunks: list[str] = []  # parallel list of text chunks


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------

def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """
    Split text into overlapping chunks by word count.
    chunk_size=512 words, overlap=50 words as specified in the task.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks


def _load_documents(docs_dir: str) -> list[str]:
    """
    Load all .txt files from the documents directory and chunk them.
    New files added to the folder are picked up automatically on next build.
    """
    all_chunks = []
    pattern = os.path.join(docs_dir, "*.txt")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"[RAG] WARNING: No .txt files found in {docs_dir}")
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            chunks = _chunk_text(content)
            all_chunks.extend(chunks)
            print(f"[RAG] Loaded {len(chunks)} chunks from {os.path.basename(fpath)}")
    return all_chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_index(docs_dir: str | None = None) -> None:
    """
    Build FAISS index from all .txt files in docs_dir.
    Called once at conversation service startup.
    """
    global _index, _chunks

    if docs_dir is None:
        docs_dir = os.path.join(os.path.dirname(__file__), "documents")

    _chunks = _load_documents(docs_dir)
    if not _chunks:
        print("[RAG] No documents loaded — RAG disabled.")
        return

    vectors = embed(_chunks)
    dim = vectors.shape[1]  # 384 for MiniLM

    _index = faiss.IndexFlatL2(dim)
    _index.add(vectors)
    print(f"[RAG] FAISS index built: {_index.ntotal} vectors, dim={dim}")


def search(query: str, k: int = 5) -> list[tuple[str, float]]:
    """
    Search the index for the top-k most relevant chunks.
    Returns list of (chunk_text, distance) tuples.
    """
    if _index is None or _index.ntotal == 0:
        return []

    query_vec = embed([query])
    distances, indices = _index.search(query_vec, k)

    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx >= 0 and idx < len(_chunks):
            results.append((_chunks[idx], float(dist)))
    return results
