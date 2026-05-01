"""
agent.py — AI agent with manual tool detection (no Groq tool calling API).

Instead of Groq's broken tool calling format, we ask the model to output
a JSON decision, parse it ourselves, run the tool, then get the final answer.
This works reliably with any prompt wording.
"""

import json
import re
import sys

from groq import Groq

import config
from tools import web_tool, location_tool

# ── Tool registry ──────────────────────────────────────────────────────────────

TOOL_EXECUTORS = {
    "find_location":    lambda args: location_tool.run(**args),
    "search_web":       lambda args: web_tool.run_search(**args),
    "scrape_webpage":   lambda args: web_tool.run_scrape(**args),
}

# ── Prompts ────────────────────────────────────────────────────────────────────

DECISION_PROMPT = """You are a pizza expert assistant tool router. You ONLY answer pizza-related questions.

Available tools:
- find_location : find pizza restaurants, pizza chains (Domino's, Pizza Hut, Papa John's, Little Caesars, etc.), opening hours, delivery places → args: {{"place_name": "pizza chain or restaurant near location"}}
- search_web    : ANYTHING about pizza — recipes, toppings, ingredients, history, calories, nutrition, dough, sauce, cheese, baking tips, pizza styles, chain menus, prices, pizza news, Greek pizza, Neapolitan pizza, any pizza type → args: {{"query": "detailed search terms", "max_results": 5}}
- no_tool       : ONLY for simple math (cost per slice, number of slices), greetings, or when you 100% already know the answer from training data → args: {{}}

Rules (follow strictly):
- ANY question about a pizza chain + location → find_location
- "near me", "nearby", "nearest", "open now", "timings", "hours" → find_location
- ANY question about pizza recipes, types, styles, toppings, ingredients, history, nutrition, how to make, baking → search_web
- Greek pizza, Neapolitan, Sicilian, Chicago, NY style, any regional pizza → search_web
- Prices, menus, chain info without location → search_web
- When in doubt → search_web (never guess, always search)
- Non-pizza questions → no_tool (politely redirect)

Respond with ONLY a single JSON object, nothing else.
Example: {{"tool": "search_web", "args": {{"query": "Greek pizza toppings and recipe", "max_results": 5}}}}

User message: {user_message}"""

ANSWER_PROMPT = """You are SLICE — a friendly pizza expert AI. Real live data was fetched and is shown below.
Give a complete, enthusiastic pizza-focused answer using ONLY that data.

STRICT RULES:
1. Answer fully — do NOT say "visit this website". Extract and present the actual information.
2. Use ONLY facts from the tool result. Do NOT invent addresses, times, or prices.
3. Format beautifully with markdown:
   - **Bold** for restaurant names, key facts, prices
   - Bullet points for multiple items or toppings
   - ### headers for sections when there's a lot of info
4. Include exact addresses, phone numbers, hours if present in the data.
5. Add a warm pizza-themed sign-off like "🍕 Enjoy your slice!" when appropriate.

User asked: {user_message}

Data fetched:
{tool_result}

Give a complete, well-formatted pizza answer now:"""

DIRECT_PROMPT = """You are SLICE — a friendly, enthusiastic pizza expert AI. You ONLY talk about pizza.

If the question is about pizza (recipes, history, types, ingredients, toppings, chains, calories, dough, sauce, cheese, baking, delivery, etc.) — answer it thoroughly and with enthusiasm.

If the question is NOT about pizza, respond warmly: "🍕 I'm SLICE, your dedicated pizza assistant! I can only help with pizza-related questions. Ask me about recipes, pizza chains near you, calories, toppings, or anything else pizza!"

Format answers with:
- **Bold** for important terms
- Bullet points for lists (toppings, steps, etc.)
- Numbers for step-by-step instructions

User: {user_message}"""


# ── Core logic ─────────────────────────────────────────────────────────────────

def _parse_tool_decision(text: str) -> dict:
    """Extract JSON tool decision from model response."""
    # Try direct JSON parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Try to find JSON block inside text
    match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {"tool": "no_tool", "args": {}}


def _extract_business_and_location(user_message: str) -> tuple[str, str]:
    """
    Parse user message like 'nearest dominos to 02125 USA' →
    returns (business_name='dominos', location='02125 USA').
    """
    import re as _re
    msg = user_message.strip()
    # Try splitting on location keywords
    split = _re.split(
        r'\b(near me|near|to this location|to zip|closest to|in zip|around me|at|to)\b',
        msg, maxsplit=1, flags=_re.IGNORECASE
    )
    if len(split) >= 3:
        business = split[0]
        location = split[2]
    else:
        business = msg
        location = ""
    # Strip leading noise words from business
    business = _re.sub(
        r'^(find|nearest|closest|get me|show me|where is|is there a|what are the)\s+',
        "", business.strip(), flags=_re.IGNORECASE
    ).strip(" ,")
    location = location.strip(" ,")
    return business, location


def _describe(tool: str, args: dict) -> str:
    labels = {
        "get_weather":      lambda a: f"Checked weather for \"{a.get('location', '')}\"",
        "find_location":    lambda a: f"Looked up location: \"{a.get('place_name', '')}\"",
        "search_web":       lambda a: f"Searched the web for \"{a.get('query', '')}\"",
        "scrape_webpage":   lambda a: f"Read webpage: {a.get('url', '')}",
        "search_documents": lambda a: f"Searched your documents for \"{a.get('query', '')}\"",
    }
    return labels.get(tool, lambda a: f"Used tool: {tool}")(args)


# ── Streaming agent (used by the UI) ──────────────────────────────────────────

def run_agent_stream(
    user_message: str,
    chat_history: list | None = None,
    groq_api_key: str | None = None,
    on_tool_call=None,
):
    api_key = groq_api_key or config.GROQ_API_KEY
    if not api_key:
        yield "Groq API key is not set. Enter your key in the sidebar."
        return

    client     = Groq(api_key=api_key)
    tools_used = []

    # ── Phase 1: Ask model which tool to use ──────────────────────────────────
    try:
        decision_resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "user", "content": DECISION_PROMPT.format(user_message=user_message)},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        decision_text = decision_resp.choices[0].message.content or ""
    except Exception as e:
        yield f"Error: {e}"
        return

    decision = _parse_tool_decision(decision_text)
    tool_name = decision.get("tool", "no_tool")
    tool_args = decision.get("args", {})

    # ── Phase 2: Execute the tool ─────────────────────────────────────────────
    import re as _re

    tool_result = ""
    if tool_name != "no_tool" and tool_name in TOOL_EXECUTORS:
        desc = _describe(tool_name, tool_args)
        tools_used.append(desc)
        if on_tool_call:
            on_tool_call(desc)
        try:
            tool_result = TOOL_EXECUTORS[tool_name](tool_args)
        except Exception as e:
            tool_result = f"Tool error: {e}"

        # After web search: always scrape top URL for real content
        if tool_name == "search_web":
            for url_match in _re.finditer(r'URL:\s*(https?://\S+)', tool_result):
                top_url = url_match.group(1)
                if any(b in top_url for b in ("google.com", "facebook.com", "twitter.com", "instagram.com")):
                    continue
                if on_tool_call:
                    on_tool_call(f"Reading full page…")
                scraped = TOOL_EXECUTORS["scrape_webpage"]({"url": top_url})
                if scraped and not scraped.startswith("Failed") and len(scraped) > 300:
                    tool_result = f"Search snippets:\n{tool_result}\n\n---\nFull page content from {top_url}:\n{scraped[:3000]}"
                    break

        # Location fallback: if OSM found nothing, search web + scrape
        if tool_name == "find_location" and (
            "No location found" in tool_result or "Could not detect" in tool_result
        ):
            from tools.location_tool import get_ip_location
            business, location = _extract_business_and_location(user_message)
            if not location:
                location = get_ip_location()
            web_query = f"{business} near {location}" if location else business

            search_desc = f'Searching web for "{web_query}"'
            tools_used.append(search_desc)
            if on_tool_call:
                on_tool_call(search_desc)
            try:
                search_result = TOOL_EXECUTORS["search_web"]({"query": web_query, "max_results": 5})
                tool_result = search_result
                for url_match in _re.finditer(r'URL:\s*(https?://\S+)', search_result):
                    top_url = url_match.group(1)
                    if any(b in top_url for b in ("google.com", "facebook.com", "twitter.com", "instagram.com")):
                        continue
                    if on_tool_call:
                        on_tool_call(f"Reading full page…")
                    scraped = TOOL_EXECUTORS["scrape_webpage"]({"url": top_url})
                    if scraped and not scraped.startswith("Failed") and len(scraped) > 300:
                        tool_result = f"Search snippets:\n{search_result}\n\n---\nFull page content from {top_url}:\n{scraped[:3000]}"
                        break
            except Exception:
                pass

    # ── Phase 3: Generate final answer ────────────────────────────────────────
    if tool_result:
        prompt = ANSWER_PROMPT.format(
            user_message=user_message,
            tool_result=tool_result,
        )
    else:
        prompt = DIRECT_PROMPT.format(user_message=user_message)

    try:
        answer_resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
        )
        answer = answer_resp.choices[0].message.content or "Sorry, I could not generate an answer."
        for word in answer.split(" "):
            yield word + " "
    except Exception as e:
        yield f"Error: {e}"


# ── Non-streaming agent (CLI test) ─────────────────────────────────────────────

def run_agent(
    user_message: str,
    chat_history: list | None = None,
    groq_api_key: str | None = None,
) -> tuple:
    api_key = groq_api_key or config.GROQ_API_KEY
    if not api_key:
        return "Groq API key is not set.", []

    client     = Groq(api_key=api_key)
    tools_used = []

    try:
        decision_resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": DECISION_PROMPT.format(user_message=user_message)}],
            temperature=0.1,
            max_tokens=200,
        )
        decision = _parse_tool_decision(decision_resp.choices[0].message.content or "")
    except Exception as e:
        return f"Error: {e}", []

    import re as _re

    tool_name = decision.get("tool", "no_tool")
    tool_args = decision.get("args", {})
    tool_result = ""

    if tool_name != "no_tool" and tool_name in TOOL_EXECUTORS:
        tools_used.append(_describe(tool_name, tool_args))
        try:
            tool_result = TOOL_EXECUTORS[tool_name](tool_args)
        except Exception as e:
            tool_result = f"Tool error: {e}"

        # After web search: always scrape top URL for real content
        if tool_name == "search_web":
            for url_match in _re.finditer(r'URL:\s*(https?://\S+)', tool_result):
                top_url = url_match.group(1)
                if any(b in top_url for b in ("google.com", "facebook.com", "twitter.com", "instagram.com")):
                    continue
                scraped = TOOL_EXECUTORS["scrape_webpage"]({"url": top_url})
                if scraped and not scraped.startswith("Failed") and len(scraped) > 300:
                    tool_result = f"Search snippets:\n{tool_result}\n\n---\nFull page content from {top_url}:\n{scraped[:3000]}"
                    break

        if tool_name == "find_location" and (
            "No location found" in tool_result or "Could not detect" in tool_result
        ):
            from tools.location_tool import get_ip_location
            business, location = _extract_business_and_location(user_message)
            if not location:
                location = get_ip_location()
            web_query = f"{business} near {location}" if location else business
            tools_used.append(f'Searching web for "{web_query}"')
            try:
                search_result = TOOL_EXECUTORS["search_web"]({"query": web_query, "max_results": 5})
                tool_result = search_result
                for url_match in _re.finditer(r'URL:\s*(https?://\S+)', search_result):
                    top_url = url_match.group(1)
                    if any(b in top_url for b in ("google.com", "facebook.com", "twitter.com", "instagram.com")):
                        continue
                    scraped = TOOL_EXECUTORS["scrape_webpage"]({"url": top_url})
                    if scraped and not scraped.startswith("Failed") and len(scraped) > 300:
                        tool_result = f"Search snippets:\n{search_result}\n\n---\nFull page content from {top_url}:\n{scraped[:3000]}"
                        break
            except Exception:
                pass

    prompt = ANSWER_PROMPT.format(user_message=user_message, tool_result=tool_result) if tool_result \
             else DIRECT_PROMPT.format(user_message=user_message)

    try:
        answer_resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
        )
        return answer_resp.choices[0].message.content or "No answer.", tools_used
    except Exception as e:
        return f"Error: {e}", tools_used


# ── CLI test ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "weather in boston"
    print(f"\nQuestion: {question}\n")
    answer, tools = run_agent(question)
    if tools:
        print("Tools used:")
        for t in tools:
            print(f"  · {t}")
        print()
    print(f"Answer:\n{answer}\n")
