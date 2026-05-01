"""tools/web_tool.py — DuckDuckGo search + BeautifulSoup web scraper."""

import requests
from bs4 import BeautifulSoup
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

import config

SEARCH_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "Search the internet using DuckDuckGo. Returns titles, URLs, and short snippets. "
            "Use this for recent news, public facts, prices, product info, or anything "
            "not in the user's uploaded documents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return (1–8). Default 5.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}

SCRAPE_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "scrape_webpage",
        "description": (
            "Fetch and read the full text of a webpage. Use this after search_web when "
            "you need detailed info from a specific URL — e.g. business hours, article "
            "body, menu items, or pricing details."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full URL to fetch."},
            },
            "required": ["url"],
        },
    },
}


def run_search(query: str, max_results: int = 5) -> str:
    """Return DuckDuckGo search results as a formatted string."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max(1, min(max_results, 8))))
    except Exception as e:
        return f"Web search failed: {e}"

    if not results:
        return "No results found for that query."

    parts = []
    for i, r in enumerate(results, 1):
        title   = r.get("title", "No title")
        href    = r.get("href", "")
        snippet = r.get("body", "")[:250]
        parts.append(f"[{i}] {title}\nURL: {href}\nSnippet: {snippet}")

    return "\n\n".join(parts)


def run_scrape(url: str) -> str:
    """Fetch a URL and return cleaned plain text content."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": config.HTTP_USER_AGENT},
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"Failed to fetch '{url}': {e}"

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text  = soup.get_text(separator="\n", strip=True)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    content = "\n".join(lines)[:3000]

    return content if content else "Could not extract readable content from this page."
