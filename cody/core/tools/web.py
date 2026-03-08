"""Web tools — webfetch, websearch."""

import ipaddress
import socket
from urllib.parse import urlparse

from pydantic_ai import RunContext

from ..deps import CodyDeps

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/internal IP address."""
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
        for _family, _type, _proto, _canonname, sockaddr in addr_infos:
            ip = ipaddress.ip_address(sockaddr[0])
            for network in _PRIVATE_NETWORKS:
                if ip in network:
                    return True
    except (socket.gaierror, ValueError, OSError):
        return False
    return False


async def webfetch(ctx: RunContext['CodyDeps'], url: str) -> str:
    """Fetch a web page and return its content as Markdown

    Args:
        url: URL to fetch (must start with http:// or https://)
    """
    from ..web import webfetch as _webfetch

    if not url.startswith(("http://", "https://")):
        return "[ERROR] URL must start with http:// or https://"

    # SSRF protection: block requests to private/internal IPs
    hostname = urlparse(url).hostname
    if hostname and _is_private_ip(hostname):
        allow_private = getattr(ctx.deps.config.security, 'allow_private_urls', False)
        if not allow_private:
            return "[ERROR] Access to private/internal URLs is blocked (SSRF protection)"

    try:
        return await _webfetch(url)
    except Exception as e:
        return f"[ERROR] Failed to fetch {url}: {e}"


async def websearch(ctx: RunContext['CodyDeps'], query: str) -> str:
    """Search the web and return results

    Args:
        query: Search query string
    """
    from ..web import websearch as _websearch

    try:
        return await _websearch(query)
    except Exception as e:
        return f"[ERROR] Web search failed: {e}"
