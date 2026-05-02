# --------------------------------------------------------------------------
# conversation/app/tools/faq_tool.py
#
# FAQ Search Tool — wraps the RAG retriever for direct FAQ queries.
# --------------------------------------------------------------------------

try:
    from ..rag.retriever import retrieve_formatted, retrieve
except ImportError:
    from rag.retriever import retrieve_formatted, retrieve


async def search_faq(query: str, k: int = 3) -> dict:
    """
    Search the clinic FAQ / knowledge base for relevant information.

    Args:
        query: The user's question
        k: Number of results to return (default 3)

    Returns:
        {"results": "formatted text"} or {"results": "", "message": "No results found"}
    """
    chunks = retrieve(query, k=k)
    if not chunks:
        return {
            "results": "",
            "message": "No relevant information found in the clinic knowledge base."
        }
    formatted = retrieve_formatted(query, k=k)
    return {"results": formatted, "count": len(chunks)}


# Tool schema
FAQ_TOOL_SCHEMA = {
    "name": "faq",
    "description": "Search the clinic knowledge base for information about doctors, hours, procedures, and policies.",
    "functions": {
        "search_faq": {"args": ["query"], "description": "Search clinic FAQ and documents"},
    }
}
