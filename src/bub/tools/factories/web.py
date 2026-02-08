"""Web tool factories."""

from __future__ import annotations

import json
from typing import cast
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import html2markdown
from republic import Tool, tool_from_model

from ...agent.context import Context
from .shared import WebFetchInput, WebSearchInput

DEFAULT_OLLAMA_WEB_API_BASE = "https://ollama.com/api"
REQUEST_TIMEOUT_SECONDS = 20
MAX_FETCH_BYTES = 1_000_000
USER_AGENT = "bub-web-tools/1.0"


def create_web_fetch_tool(_context: Context) -> Tool:
    """Create a web fetch tool that returns markdown converted from HTML."""

    def _handler(params: WebFetchInput) -> str:
        url = _normalize_url(params.url)
        if not url:
            return "error: invalid url"

        request = urllib_request.Request(  # noqa: S310 - scheme is validated by _normalize_url.
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib_request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                body_bytes = response.read(MAX_FETCH_BYTES + 1)
                truncated = len(body_bytes) > MAX_FETCH_BYTES
                if truncated:
                    body_bytes = body_bytes[:MAX_FETCH_BYTES]
                charset = response.headers.get_content_charset() or "utf-8"
        except urllib_error.URLError as exc:
            return f"error: {exc!s}"
        except OSError as exc:
            return f"error: {exc!s}"

        html = body_bytes.decode(charset, errors="replace")
        markdown = html2markdown.convert(html).strip()
        if not markdown:
            return "error: empty response body"
        if truncated:
            return f"{markdown}\n\n[truncated: response exceeded byte limit]"
        return cast(str, markdown)

    return tool_from_model(
        WebFetchInput,
        _handler,
        name="web.fetch",
        description="Fetch a URL and convert HTML to markdown",
    )


def create_web_search_tool(context: Context) -> Tool:
    """Create a web search tool powered by Ollama web search API."""

    def _handler(params: WebSearchInput) -> str:
        api_key = context.settings.ollama_api_key or context.settings.api_key
        if not api_key:
            return "error: ollama api key is not configured"

        api_base = _normalize_api_base(context.settings.ollama_api_base or DEFAULT_OLLAMA_WEB_API_BASE)
        if not api_base:
            return "error: invalid ollama api base url"

        endpoint = f"{api_base}/web_search"
        payload = {
            "query": params.query,
            "max_results": params.max_results,
        }
        request = urllib_request.Request(  # noqa: S310 - endpoint derives from validated api base.
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )

        try:
            with urllib_request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                response_body = response.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            if detail:
                return f"error: http {exc.code}: {detail}"
            return f"error: http {exc.code}"
        except urllib_error.URLError as exc:
            return f"error: {exc!s}"
        except OSError as exc:
            return f"error: {exc!s}"

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            return f"error: invalid json response: {exc!s}"

        results = data.get("results")
        if not isinstance(results, list) or not results:
            return "none"
        return _format_search_results(results)

    return tool_from_model(
        WebSearchInput,
        _handler,
        name="web.search",
        description="Search the web via Ollama web search API",
    )


def _normalize_url(raw_url: str) -> str | None:
    normalized = raw_url.strip()
    if not normalized:
        return None

    parsed = urllib_parse.urlparse(normalized)
    if parsed.scheme and parsed.netloc:
        if parsed.scheme not in {"http", "https"}:
            return None
        return normalized

    if parsed.scheme == "" and parsed.netloc == "" and parsed.path:
        with_scheme = f"https://{normalized}"
        parsed = urllib_parse.urlparse(with_scheme)
        if parsed.netloc:
            return with_scheme

    return None


def _format_search_results(results: list[object]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "(untitled)")
        url = str(item.get("url") or "")
        content = str(item.get("content") or "")
        lines.append(f"{idx}. {title}")
        if url:
            lines.append(f"   {url}")
        if content:
            lines.append(f"   {content}")

    return "\n".join(lines) if lines else "none"


def _normalize_api_base(raw_api_base: str) -> str | None:
    normalized = raw_api_base.strip().rstrip("/")
    if not normalized:
        return None

    parsed = urllib_parse.urlparse(normalized)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return normalized
    return None
