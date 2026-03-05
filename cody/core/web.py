"""Web capabilities: fetch web pages and search the web.

Provides webfetch and websearch tools for the Cody agent.
"""

import json
import logging
import re
from html.parser import HTMLParser
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── HTML → Markdown converter ────────────────────────────────────────────────


class _HTMLToMarkdown(HTMLParser):
    """Minimal HTML to Markdown converter."""

    def __init__(self):
        super().__init__()
        self._result: list[str] = []
        self._skip_depth = 0
        self._in_pre = False
        self._in_code = False
        self._link_href: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attrs_dict = dict(attrs)
        tag = tag.lower()

        if tag in ("script", "style", "nav", "footer", "header", "noscript"):
            self._skip_depth += 1
            return

        if self._skip_depth > 0:
            return

        if tag == "h1":
            self._result.append("\n# ")
        elif tag == "h2":
            self._result.append("\n## ")
        elif tag == "h3":
            self._result.append("\n### ")
        elif tag in ("h4", "h5", "h6"):
            self._result.append("\n#### ")
        elif tag == "p":
            self._result.append("\n\n")
        elif tag == "br":
            self._result.append("\n")
        elif tag == "li":
            self._result.append("\n- ")
        elif tag == "pre":
            self._result.append("\n```\n")
            self._in_pre = True
        elif tag == "code" and not self._in_pre:
            self._result.append("`")
            self._in_code = True
        elif tag == "a":
            self._link_href = attrs_dict.get("href")
            self._result.append("[")
        elif tag in ("strong", "b"):
            self._result.append("**")
        elif tag in ("em", "i"):
            self._result.append("*")
        elif tag == "blockquote":
            self._result.append("\n> ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in ("script", "style", "nav", "footer", "header", "noscript"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return

        if self._skip_depth > 0:
            return

        if tag == "pre":
            self._result.append("\n```\n")
            self._in_pre = False
        elif tag == "code" and self._in_code:
            self._result.append("`")
            self._in_code = False
        elif tag == "a":
            if self._link_href:
                self._result.append(f"]({self._link_href})")
            else:
                self._result.append("]")
            self._link_href = None
        elif tag in ("strong", "b"):
            self._result.append("**")
        elif tag in ("em", "i"):
            self._result.append("*")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._result.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        self._result.append(data)

    def get_markdown(self) -> str:
        text = "".join(self._result)
        # Clean up excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str) -> str:
    """Convert HTML to readable Markdown."""
    parser = _HTMLToMarkdown()
    parser.feed(html)
    return parser.get_markdown()


# ── Web fetch ────────────────────────────────────────────────────────────────


_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CodyBot/1.0.0; "
        "+https://github.com/SUT-GC/cody)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MAX_CONTENT_LENGTH = 500_000  # 500KB max


async def webfetch(url: str, timeout: float = 15.0) -> str:
    """Fetch a web page and convert to Markdown.

    Args:
        url: URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Markdown content of the page, or error string.
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers=_DEFAULT_HEADERS,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        if "text/html" in content_type or "application/xhtml" in content_type:
            html = resp.text[:MAX_CONTENT_LENGTH]
            return html_to_markdown(html)
        if "text/plain" in content_type or "text/markdown" in content_type:
            return resp.text[:MAX_CONTENT_LENGTH]
        if "application/json" in content_type:
            try:
                data = resp.json()
                return json.dumps(data, indent=2, ensure_ascii=False)[:MAX_CONTENT_LENGTH]
            except Exception:
                return resp.text[:MAX_CONTENT_LENGTH]
        return f"[Unsupported content type: {content_type}]"


# ── Web search ───────────────────────────────────────────────────────────────

# We use DuckDuckGo HTML search (no API key required)
_DDG_URL = "https://html.duckduckgo.com/html/"


async def websearch(query: str, max_results: int = 8, timeout: float = 10.0) -> str:
    """Search the web using DuckDuckGo.

    Args:
        query: Search query string.
        max_results: Max number of results to return.
        timeout: Request timeout.

    Returns:
        Formatted search results as text.
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers=_DEFAULT_HEADERS,
    ) as client:
        resp = await client.post(
            _DDG_URL,
            data={"q": query, "b": ""},
        )
        resp.raise_for_status()

    html = resp.text
    results = _parse_ddg_results(html, max_results)

    if not results:
        return f"No search results found for: {query}"

    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r['title']}**")
        if r["url"]:
            lines.append(f"   {r['url']}")
        if r["snippet"]:
            lines.append(f"   {r['snippet']}")
        lines.append("")

    return "\n".join(lines)


def _parse_ddg_results(html: str, max_results: int) -> list[dict]:
    """Parse DuckDuckGo HTML search results."""
    results: list[dict] = []

    # Extract result blocks — DuckDuckGo uses <a class="result__a"> for titles
    # and <a class="result__snippet"> for snippets
    title_pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'class="result__snippet"[^>]*>(.*?)</(?:a|span)>',
        re.DOTALL,
    )

    titles = title_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (url, title_html) in enumerate(titles[:max_results]):
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()

        # DuckDuckGo wraps URLs in a redirect; extract the actual URL
        if "uddg=" in url:
            import urllib.parse
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            url = parsed.get("uddg", [url])[0]

        results.append({"title": title, "url": url, "snippet": snippet})

    return results
