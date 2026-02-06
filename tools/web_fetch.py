"""Web fetch tool for retrieving page content."""

from __future__ import annotations

import json
import logging

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

WEB_FETCH_TOOL = {
    "name": "web_fetch",
    "description": (
        "Fetch the content of a web page and extract its text. Use this to read "
        "SEC filings, earnings transcripts, analyst reports, and other web pages "
        "found via web_search. Returns the page text content (HTML stripped)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch.",
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum characters to return (default 50000). Truncates from the end.",
                "default": 50000,
            },
        },
        "required": ["url"],
    },
}


def execute_web_fetch(url: str, max_length: int = 50000) -> str:
    """Fetch a web page and extract text content."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        if "json" in content_type:
            text = response.text[:max_length]
            return json.dumps({"url": url, "content_type": "json", "content": text})

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # Collapse multiple newlines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = "\n".join(lines)

        if len(text) > max_length:
            text = text[:max_length] + "\n\n[TRUNCATED]"

        return json.dumps({
            "url": url,
            "content_type": "html",
            "length": len(text),
            "content": text,
        })

    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"HTTP {e.response.status_code}: {url}"})
    except httpx.TimeoutException:
        return json.dumps({"error": f"Timeout fetching {url}"})
    except Exception as e:
        logger.exception("Web fetch failed")
        return json.dumps({"error": f"Fetch failed: {str(e)}"})
