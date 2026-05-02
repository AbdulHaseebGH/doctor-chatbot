# --------------------------------------------------------------------------
# conversation/app/rag/embedder.py
#
# Singleton loader for the all-MiniLM-L6-v2 sentence embedding model.
# Loaded once at import time; used by vector_store and retriever.
# --------------------------------------------------------------------------

from sentence_transformers import SentenceTransformer
import numpy as np

_model = None


def get_embedder() -> SentenceTransformer:
    """Return the singleton SentenceTransformer model."""
    global _model
    if _model is None:
        print("[RAG] Loading embedding model: all-MiniLM-L6-v2 ...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[RAG] Embedding model loaded.")
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """
    Embed a list of strings into a 2D numpy array of shape (N, 384).
    Uses batch encoding for efficiency.
    """
    model = get_embedder()
    vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return vectors.astype(np.float32)
