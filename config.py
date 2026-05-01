import os

# Database — ChromaDB writes SQLite + HNSW index files here
DB_PATH = "./chroma_db"

# Collection names (two collections because text and image models
# produce different vector dimensions and cannot share a collection)
TEXT_COLLECTION  = "text_documents"   # sentence-transformers → 384-dim
IMAGE_COLLECTION = "image_files"      # OpenCLIP ViT-B-32     → 512-dim

# Text embedding model — runs locally, no API key, ~90 MB download on first use
TEXT_MODEL = "all-MiniLM-L6-v2"

# Image embedding model — ViT-B-32 with laion2b checkpoint (~350 MB download)
# Both text queries and images embed into the same 512-dim CLIP space,
# enabling cross-modal search (find images with a text description).
CLIP_MODEL      = "ViT-B-32"
CLIP_CHECKPOINT = "laion2b_s34b_b79k"

# Supported file extensions
TEXT_EXTENSIONS  = {".txt", ".pdf", ".docx", ".csv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

# all-MiniLM-L6-v2 has a 256-token limit; truncating at 2000 chars is a safe
# simplification for a beginner project (production would use chunking)
MAX_TEXT_CHARS = 2000

DEFAULT_N_RESULTS = 3

# ── Agent / LLM settings ──────────────────────────────────────────────────────

# Groq API key — set here OR as environment variable GROQ_API_KEY
# Get a free key at https://console.groq.com
# Key priority: Streamlit Secrets → env var → empty (user enters in sidebar)
def _load_groq_key() -> str:
    try:
        import streamlit as st
        return st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        pass
    return os.getenv("GROQ_API_KEY", "")

GROQ_API_KEY = _load_groq_key()

# Groq model with tool/function calling support
GROQ_MODEL = "llama-3.3-70b-versatile"

# Max tool-call iterations before the agent gives up
AGENT_MAX_ITERATIONS = 5

# RAG: discard results below this similarity score to avoid hallucination
RAG_SIMILARITY_THRESHOLD = 0.35
RAG_TOP_K = 3

# HTTP timeout (seconds) for web scraping and external APIs
HTTP_TIMEOUT = 10

# Polite User-Agent header for web requests
HTTP_USER_AGENT = "Mozilla/5.0 (compatible; VectorDBChatbot/1.0)"
