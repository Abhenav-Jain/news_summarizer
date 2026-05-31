"""
Core logic for the News Summarizer application.

Pipeline:
  topic -> Tavily web search -> Mistral analysis -> structured result

The analysis returns not just a summary but also sentiment and key entities,
all in a single LLM call (cheaper than three separate calls). Results are
cached in SQLite so repeated queries stay on the free tier.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List

from dotenv import load_dotenv

from langchain_tavily import TavilySearch
from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

import cache

load_dotenv()
cache.init_db()


# --------------------------------------------------------------------------- #
# Config / key validation
# --------------------------------------------------------------------------- #
def _require_keys() -> None:
    missing = [
        name
        for name in ("TAVILY_API_KEY", "MISTRAL_API_KEY")
        if not os.getenv(name)
    ]
    if missing:
        raise EnvironmentError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Add them to a .env file or your shell environment."
        )


@lru_cache(maxsize=None)
def get_search_tool(max_results: int = 5) -> TavilySearch:
    _require_keys()
    return TavilySearch(max_results=max_results)


@lru_cache(maxsize=None)
def get_llm(model: str = "mistral-small-2506", temperature: float = 0.3) -> ChatMistralAI:
    _require_keys()
    return ChatMistralAI(model=model, temperature=temperature)


# --------------------------------------------------------------------------- #
# Prompt: ask for everything in one structured JSON response
# --------------------------------------------------------------------------- #
ANALYSIS_PROMPT = """You are a professional news analyst.

Analyze the search results below about "{topic}" and respond with ONLY a valid
JSON object (no markdown, no backticks, no preamble) with this exact schema:

{{
  "headline": "one-line overall summary of the situation",
  "bullets": ["5 to 8 concise single-sentence key facts"],
  "takeaway": "one short key-takeaway sentence",
  "sentiment": {{
     "label": "Positive | Neutral | Negative | Mixed",
     "score": <number from -1.0 (very negative) to 1.0 (very positive)>,
     "reason": "one short sentence explaining the sentiment"
  }},
  "entities": {{
     "people": ["notable people mentioned"],
     "organizations": ["notable organizations/companies"],
     "locations": ["notable places"]
  }}
}}

Rules:
- Base everything strictly on the search results; do not invent facts.
- If a category has nothing, use an empty list.
- Keep bullets factual and non-repetitive.

Search results:
{news}
"""


@lru_cache(maxsize=None)
def get_chain(model: str = "mistral-small-2506", temperature: float = 0.3):
    prompt = ChatPromptTemplate.from_template(ANALYSIS_PROMPT)
    return prompt | get_llm(model=model, temperature=temperature) | StrOutputParser()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def fetch_news(topic: str, max_results: int = 5) -> List[Dict[str, Any]]:
    tool = get_search_tool(max_results=max_results)
    raw = tool.invoke({"query": topic})
    if isinstance(raw, dict):
        return raw.get("results", [])
    if isinstance(raw, list):
        return raw
    return []


def _safe_json(text: str) -> Dict[str, Any]:
    """Parse model output into JSON, tolerating stray markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # strip ```json ... ``` fences
        cleaned = cleaned.split("```", 2)[1] if "```" in cleaned else cleaned
        cleaned = cleaned.replace("json", "", 1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # last-ditch: find the first { ... } block
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
    # graceful fallback so the UI never crashes
    return {
        "headline": "Summary could not be parsed.",
        "bullets": [cleaned[:500]],
        "takeaway": "",
        "sentiment": {"label": "Neutral", "score": 0.0, "reason": ""},
        "entities": {"people": [], "organizations": [], "locations": []},
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def analyze_topic(
    topic: str,
    max_results: int = 5,
    model: str = "mistral-small-2506",
    temperature: float = 0.3,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Search the web for `topic`, analyze it, and return a structured result:

    {
      "topic", "headline", "bullets", "takeaway",
      "sentiment": {...}, "entities": {...},
      "sources": [{title, url}], "cached": bool
    }
    """
    if not topic or not topic.strip():
        raise ValueError("Topic must be a non-empty string.")

    topic = topic.strip()

    if use_cache:
        hit = cache.get_cached(topic, model, max_results)
        if hit:
            hit["cached"] = True
            return hit

    results = fetch_news(topic, max_results=max_results)
    if not results:
        empty = {
            "topic": topic,
            "headline": "No results found.",
            "bullets": ["Try rephrasing or broadening your query."],
            "takeaway": "",
            "sentiment": {"label": "Neutral", "score": 0.0, "reason": ""},
            "entities": {"people": [], "organizations": [], "locations": []},
            "sources": [],
            "cached": False,
        }
        return empty

    news_block = "\n\n".join(
        f"Title: {r.get('title', 'Untitled')}\n"
        f"URL: {r.get('url', '')}\n"
        f"Content: {r.get('content', '')}"
        for r in results
    )

    raw_out = get_chain(model=model, temperature=temperature).invoke(
        {"topic": topic, "news": news_block}
    )
    parsed = _safe_json(raw_out)

    sources = [
        {"title": r.get("title", "Untitled"), "url": r.get("url", "")}
        for r in results
        if r.get("url")
    ]

    result = {
        "topic": topic,
        "headline": parsed.get("headline", ""),
        "bullets": parsed.get("bullets", []),
        "takeaway": parsed.get("takeaway", ""),
        "sentiment": parsed.get(
            "sentiment", {"label": "Neutral", "score": 0.0, "reason": ""}
        ),
        "entities": parsed.get(
            "entities", {"people": [], "organizations": [], "locations": []}
        ),
        "sources": sources,
        "cached": False,
    }

    if use_cache:
        cache.save_result(topic, model, max_results, result)

    return result


def compare_topics(
    topics: List[str],
    max_results: int = 5,
    model: str = "mistral-small-2506",
    temperature: float = 0.3,
) -> List[Dict[str, Any]]:
    """Analyze several topics so the UI can show them side by side."""
    return [
        analyze_topic(t, max_results=max_results, model=model, temperature=temperature)
        for t in topics
        if t and t.strip()
    ]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) or "Latest world news today"
    out = analyze_topic(query)
    print(f"\n{out['headline']}\n" + "-" * 60)
    for b in out["bullets"]:
        print(f"- {b}")
    print(f"\nSentiment: {out['sentiment']['label']} ({out['sentiment']['score']})")
    print(f"Takeaway: {out['takeaway']}")