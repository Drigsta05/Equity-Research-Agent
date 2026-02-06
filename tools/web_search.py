"""Web search tool using DuckDuckGo."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for information. Returns a list of results with titles, "
        "URLs, and snippets. Use this to find financial data, SEC filings, "
        "earnings reports, analyst coverage, industry data, and company information."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Be specific: include company name, ticker, and what you're looking for.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 10, max 20).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}


def execute_web_search(query: str, max_results: int = 10) -> str:
    """Execute a web search using DuckDuckGo."""
    max_results = min(max_results, 20)
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return json.dumps({"results": [], "message": "No results found."})

        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", r.get("link", "")),
                "snippet": r.get("body", r.get("snippet", "")),
            })

        return json.dumps({"results": formatted}, indent=2)

    except ImportError:
        return json.dumps({
            "error": "duckduckgo-search package not installed. Run: pip install duckduckgo-search"
        })
    except Exception as e:
        logger.exception("Web search failed")
        return json.dumps({"error": f"Search failed: {str(e)}"})
