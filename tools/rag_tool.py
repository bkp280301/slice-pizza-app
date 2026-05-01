"""tools/rag_tool.py — Search the local ChromaDB for relevant documents."""

import config
from query import search_text

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
                    "description": "The semantic search query — rephrase as a factual question.",
                }
            },
            "required": ["query"],
        },
    },
}


def run(query: str) -> str:
    """Execute RAG search and return a formatted string for the LLM."""
    try:
        results = search_text(query, n_results=config.RAG_TOP_K)
    except FileNotFoundError:
        return "Document database not initialized. No documents ingested yet."
    except Exception as e:
        return f"RAG search error: {e}"

    results = [r for r in results if r["similarity"] >= config.RAG_SIMILARITY_THRESHOLD]

    if not results:
        return "No relevant documents found in the local database for this query."

    parts = []
    for i, r in enumerate(results, 1):
        meta     = r.get("metadata") or {}
        filename = meta.get("filename", "unknown file")
        snippet  = (r.get("document") or "")[:600].replace("\n", " ")
        score    = r["similarity"]
        parts.append(f"[Document {i} | File: {filename} | Relevance: {score:.2f}]\n{snippet}")

    return "\n\n".join(parts)
