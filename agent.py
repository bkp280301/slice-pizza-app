"""
agent.py — SLICE pizza agent. Uses web search with LLM-knowledge fallback.
"""

import json
import re
import sys

from groq import Groq

import config
from tools import web_tool, location_tool

# ── Tool registry ─────────────────────────────────────────────────────────────
TOOL_EXECUTORS = {
    "find_location": lambda args: location_tool.run(**args),
    "search_web":    lambda args: web_tool.run_search(**args),
    "scrape_webpage":lambda args: web_tool.run_scrape(**args),
}

# ── Prompts ───────────────────────────────────────────────────────────────────
DECISION_PROMPT = """You are a pizza assistant tool router.

Tools:
- find_location : pizza restaurants/chains near a location → args: {{"place_name": "chain near city/zip"}}
- search_web    : recipes, toppings, ingredients, history, calories, styles, menus, prices → args: {{"query": "...", "max_results": 5}}
- no_tool       : simple math, greetings, non-pizza questions → args: {{}}

Rules:
- Location/hours/open now/nearest → find_location
- Recipes, toppings, ingredients, history, nutrition, any pizza style → search_web
- Non-pizza → no_tool

Reply with ONLY JSON. Example: {{"tool": "search_web", "args": {{"query": "Greek pizza toppings", "max_results": 5}}}}

User: {user_message}"""

ANSWER_PROMPT = """You are SLICE — an enthusiastic pizza expert AI.
Use the data below to give a rich, complete answer. Never say "visit the website" — extract and present the actual info.

Format with markdown: **bold** key facts, bullet lists for toppings/steps, ### headers for sections.
End with: 🍕 Enjoy your slice!

User asked: {user_message}

Live data:
{tool_result}

Answer now:"""

DIRECT_PROMPT = """You are SLICE — a passionate pizza expert AI with deep knowledge of everything pizza.

Answer the question thoroughly using your own extensive pizza knowledge.
Cover: ingredients, history, regional styles, tips, fun facts — whatever is relevant.

Format with markdown: **bold** key terms, bullet lists, numbered steps.
End with: 🍕 Enjoy your slice!

If the question is NOT about pizza at all, say:
"🍕 I'm SLICE, your pizza expert! I only answer pizza questions. Ask me about recipes, chains, calories, or toppings!"

User: {user_message}"""

LOCATION_FALLBACK_PROMPT = """You are SLICE — a pizza expert AI.

The user is looking for pizza near: {location}
Live map data was unavailable, but use your knowledge to give a genuinely useful answer.

DO NOT say "use Google Maps", "use Yelp", or "search online" — that is unhelpful.
INSTEAD give:
1. 5–6 major pizza chains very likely to have a location near {location} (Domino's, Pizza Hut, Papa John's, Little Caesars, Sbarro, etc.) — pick ones you know are common in that region
2. For each chain: their **ordering app/website** (e.g. dominos.com, order.pizzahut.com) and phone ordering
3. Whether the chain typically delivers or is dine-in/takeout
4. Any well-known local or regional chains specific to that area if you know them

Format as a bulleted list with **bold chain names**. End with: 🍕 Enjoy your slice!

User asked: {user_message}"""


def _search_failed(result: str) -> bool:
    """Return True if web search gave us nothing useful."""
    if not result:
        return True
    bad = [
        "no results found", "web search failed", "tool error",
        "could not extract", "failed to fetch", "not available",
        "0 results", "unable to find"
    ]
    return any(b in result.lower() for b in bad)


def _parse_tool_decision(text: str) -> dict:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"tool": "no_tool", "args": {}}


def _extract_business_and_location(user_message: str) -> tuple[str, str]:
    msg = user_message.strip()
    split = re.split(
        r'\b(near me|near|to this location|to zip|closest to|in zip|around me|at|to)\b',
        msg, maxsplit=1, flags=re.IGNORECASE
    )
    if len(split) >= 3:
        business, location = split[0], split[2]
    else:
        business, location = msg, ""
    business = re.sub(
        r'^(find|nearest|closest|get me|show me|where is|is there a|what are the)\s+',
        "", business.strip(), flags=re.IGNORECASE
    ).strip(" ,")
    return business, location.strip(" ,")


def _describe(tool: str, args: dict) -> str:
    labels = {
        "find_location": lambda a: f"Looking up \"{a.get('place_name', '')}\"",
        "search_web":    lambda a: f"Searching \"{a.get('query', '')}\"",
        "scrape_webpage":lambda a: f"Reading page…",
    }
    return labels.get(tool, lambda a: f"Using {tool}")(args)


def _run_web_and_scrape(query: str, max_results: int = 5, on_tool_call=None) -> str:
    """Run web search + scrape top URL. Returns best available result."""
    try:
        result = TOOL_EXECUTORS["search_web"]({"query": query, "max_results": max_results})
    except Exception as e:
        return ""

    if _search_failed(result):
        return ""

    # Try scraping the top URL for richer content
    for url_match in re.finditer(r'URL:\s*(https?://\S+)', result):
        top_url = url_match.group(1)
        if any(b in top_url for b in ("google.com", "facebook.com", "twitter.com", "instagram.com", "youtube.com")):
            continue
        if on_tool_call:
            on_tool_call("Reading full page…")
        try:
            scraped = TOOL_EXECUTORS["scrape_webpage"]({"url": top_url})
            if scraped and not scraped.startswith("Failed") and len(scraped) > 300:
                return f"Search results:\n{result}\n\n---\nFull article from {top_url}:\n{scraped[:3000]}"
        except Exception:
            pass
        break

    return result


# ── Streaming agent ───────────────────────────────────────────────────────────
def run_agent_stream(
    user_message: str,
    chat_history: list | None = None,
    groq_api_key: str | None = None,
    on_tool_call=None,
):
    api_key = groq_api_key or config.GROQ_API_KEY
    if not api_key:
        yield "Groq API key is not set. Enter your key in Settings (sidebar)."
        return

    client = Groq(api_key=api_key)

    # Phase 1 — decide tool
    try:
        dec = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": DECISION_PROMPT.format(user_message=user_message)}],
            temperature=0.1,
            max_tokens=150,
        )
        decision = _parse_tool_decision(dec.choices[0].message.content or "")
    except Exception as e:
        yield f"Error contacting AI: {e}"
        return

    tool_name = decision.get("tool", "no_tool")
    tool_args = decision.get("args", {})
    tool_result = ""

    # Phase 2 — run tool
    if tool_name == "search_web":
        query = tool_args.get("query", user_message)
        if on_tool_call:
            on_tool_call(f"Searching \"{query}\"")
        tool_result = _run_web_and_scrape(query, on_tool_call=on_tool_call)

    elif tool_name == "find_location":
        place_name = tool_args.get("place_name", user_message)
        if on_tool_call:
            on_tool_call(f"Checking map data for \"{place_name}\"")
        try:
            osm_result = TOOL_EXECUTORS["find_location"](tool_args)
        except Exception:
            osm_result = ""

        # Always supplement with a targeted web search — chain store locators
        # give far more accurate and up-to-date results than OSM data.
        business, location = _extract_business_and_location(user_message)
        if not location:
            try:
                location = location_tool.get_ip_location()
            except Exception:
                location = ""
        web_query = f"{business} pizza near {location} address hours" if location else f"{business} pizza locations"
        if on_tool_call:
            on_tool_call(f"Searching web for \"{web_query}\"")
        web_result = _run_web_and_scrape(web_query, on_tool_call=on_tool_call)

        if osm_result and not _search_failed(osm_result):
            # Merge OSM + web
            tool_result = osm_result
            if web_result and not _search_failed(web_result):
                tool_result += f"\n\n---\nAdditional web results:\n{web_result}"
        else:
            tool_result = web_result

    # Phase 3 — generate answer
    if tool_result and not _search_failed(tool_result):
        prompt = ANSWER_PROMPT.format(user_message=user_message, tool_result=tool_result)
    elif tool_name == "find_location":
        # Location-specific fallback: list real chains + ordering apps, never say "use Google Maps"
        _, loc = _extract_business_and_location(user_message)
        if not loc:
            try:
                loc = location_tool.get_ip_location()
            except Exception:
                loc = "your area"
        prompt = LOCATION_FALLBACK_PROMPT.format(
            user_message=user_message,
            location=loc or "your area",
        )
    else:
        prompt = DIRECT_PROMPT.format(user_message=user_message)

    try:
        ans = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2048,
        )
        answer = ans.choices[0].message.content or "Sorry, I could not generate an answer."
        for word in answer.split(" "):
            yield word + " "
    except Exception as e:
        yield f"Error: {e}"


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "what toppings are good for greek pizza"
    print(f"\nQuestion: {question}\n")

    api_key = config.GROQ_API_KEY
    if not api_key:
        print("No API key set.")
        sys.exit(1)

    client = Groq(api_key=api_key)
    dec = _parse_tool_decision(
        client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": DECISION_PROMPT.format(user_message=question)}],
            temperature=0.1, max_tokens=150,
        ).choices[0].message.content or ""
    )
    print(f"Tool decision: {dec}\n")

    tool_result = ""
    if dec.get("tool") == "search_web":
        tool_result = _run_web_and_scrape(dec["args"].get("query", question))

    prompt = ANSWER_PROMPT.format(user_message=question, tool_result=tool_result) \
             if (tool_result and not _search_failed(tool_result)) \
             else DIRECT_PROMPT.format(user_message=question)

    ans = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4, max_tokens=2048,
    )
    print(ans.choices[0].message.content)
