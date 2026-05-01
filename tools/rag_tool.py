"""tools/rag_tool.py — Search the local ChromaDB for relevant documents."""

try:
    import config
    from query import search_text
    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": (
            "Search the user's uploaded documents stored in the local vector database. "
            "Use this when the question is about uploaded files, contracts, personal "
            "documents, previously ingested data, or any private/internal information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The semantic search query.",
                }
            },
            "required": ["query"],
        },
    },
}


def run(query: str) -> str:
    if not _RAG_AVAILABLE:
        return "Document search is not available in this environment."
    try:
        import config as _config
        results = search_text(query, n_results=_config.RAG_TOP_K)
    except Exception as e:
        return f"RAG search error: {e}"

    results = [r for r in results if r["similarity"] >= _config.RAG_SIMILARITY_THRESHOLD]
    if not results:
        return "No relevant documents found for this query."

    parts = []
    for i, r in enumerate(results, 1):
        meta     = r.get("metadata") or {}
        filename = meta.get("filename", "unknown file")
        snippet  = (r.get("document") or "")[:600].replace("\n", " ")
        score    = r["similarity"]
        parts.append(f"[Document {i} | File: {filename} | Relevance: {score:.2f}]\n{snippet}")
    return "\n\n".join(parts)
