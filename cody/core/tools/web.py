"""Web tools — webfetch, websearch.

SSRF protection is handled in core/web.py (_is_private_url).
"""

from pydantic_ai import RunContext

from ..deps import CodyDeps


async def webfetch(ctx: RunContext['CodyDeps'], url: str) -> str:
    """Fetch a web page and return its content as Markdown

    Args:
        url: URL to fetch (must start with http:// or https://)
    """
    from ..web import webfetch as _webfetch

    if not url.startswith(("http://", "https://")):
        return "[ERROR] URL must start with http:// or https://"

    return await _webfetch(url)


async def websearch(ctx: RunContext['CodyDeps'], query: str) -> str:
    """Search the web and return results

    Args:
        query: Search query string
    """
    from ..web import websearch as _websearch

    return await _websearch(query)
