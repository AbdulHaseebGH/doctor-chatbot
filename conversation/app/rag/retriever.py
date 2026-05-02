# --------------------------------------------------------------------------
# conversation/app/rag/retriever.py
#
# Public interface for RAG retrieval.
# Returns top-k relevant text chunks for a given query.
# --------------------------------------------------------------------------

from .vector_store import search

# Distance threshold — chunks with L2 distance above this are too dissimilar
MAX_DISTANCE = 2.5


def retrieve(query: str, k: int = 3) -> list[str]:
    """
    Retrieve the top-k most relevant document chunks for a query.

    Args:
        query: The user's question or message.
        k: Number of chunks to return (default 3).

    Returns:
        List of relevant text strings, filtered by distance threshold.
        Returns empty list if RAG index is not built or no good matches.
    """
    results = search(query, k=k)
    filtered = [chunk for chunk, dist in results if dist < MAX_DISTANCE]
    return filtered


def retrieve_formatted(query: str, k: int = 3) -> str:
    """
    Retrieve and format relevant chunks into a single string for prompt injection.
    Returns empty string if no relevant documents found.
    """
    chunks = retrieve(query, k=k)
    if not chunks:
        return ""
    formatted = "\n\n---\n\n".join(f"[Reference {i+1}]\n{chunk}" for i, chunk in enumerate(chunks))
    return formatted
