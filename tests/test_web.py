"""Tests for web capabilities module"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from cody.core.web import (
    html_to_markdown,
    webfetch,
    websearch,
    _parse_ddg_results,
)


# ── html_to_markdown ─────────────────────────────────────────────────────────


def test_html_to_markdown_headings():
    html = "<h1>Title</h1><h2>Subtitle</h2><h3>Section</h3>"
    md = html_to_markdown(html)
    assert "# Title" in md
    assert "## Subtitle" in md
    assert "### Section" in md


def test_html_to_markdown_paragraphs():
    html = "<p>First paragraph</p><p>Second paragraph</p>"
    md = html_to_markdown(html)
    assert "First paragraph" in md
    assert "Second paragraph" in md


def test_html_to_markdown_links():
    html = '<a href="https://example.com">Click here</a>'
    md = html_to_markdown(html)
    assert "[Click here](https://example.com)" in md


def test_html_to_markdown_bold_italic():
    html = "<strong>bold</strong> and <em>italic</em>"
    md = html_to_markdown(html)
    assert "**bold**" in md
    assert "*italic*" in md


def test_html_to_markdown_code():
    html = "<code>inline code</code>"
    md = html_to_markdown(html)
    assert "`inline code`" in md


def test_html_to_markdown_pre():
    html = "<pre>code block</pre>"
    md = html_to_markdown(html)
    assert "```" in md
    assert "code block" in md


def test_html_to_markdown_list():
    html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
    md = html_to_markdown(html)
    assert "- Item 1" in md
    assert "- Item 2" in md


def test_html_to_markdown_skips_script():
    html = "<p>Visible</p><script>alert('hidden')</script><p>Also visible</p>"
    md = html_to_markdown(html)
    assert "Visible" in md
    assert "Also visible" in md
    assert "alert" not in md


def test_html_to_markdown_skips_style():
    html = "<style>body { color: red; }</style><p>Content</p>"
    md = html_to_markdown(html)
    assert "Content" in md
    assert "color" not in md


def test_html_to_markdown_blockquote():
    html = "<blockquote>Quoted text</blockquote>"
    md = html_to_markdown(html)
    assert "> Quoted text" in md


def test_html_to_markdown_empty():
    assert html_to_markdown("") == ""


def test_html_to_markdown_br():
    html = "Line1<br>Line2"
    md = html_to_markdown(html)
    assert "Line1\nLine2" in md


# ── webfetch ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webfetch_html():
    mock_resp = MagicMock()
    mock_resp.text = "<html><body><h1>Hello</h1><p>World</p></body></html>"
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cody.core.web.httpx.AsyncClient", return_value=mock_client):
        result = await webfetch("https://example.com")

    assert "Hello" in result
    assert "World" in result


@pytest.mark.asyncio
async def test_webfetch_json():
    mock_resp = MagicMock()
    mock_resp.text = '{"key": "value"}'
    mock_resp.json = MagicMock(return_value={"key": "value"})
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cody.core.web.httpx.AsyncClient", return_value=mock_client):
        result = await webfetch("https://api.example.com/data")

    assert '"key"' in result
    assert '"value"' in result


@pytest.mark.asyncio
async def test_webfetch_plain_text():
    mock_resp = MagicMock()
    mock_resp.text = "Just plain text"
    mock_resp.headers = {"content-type": "text/plain"}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cody.core.web.httpx.AsyncClient", return_value=mock_client):
        result = await webfetch("https://example.com/file.txt")

    assert result == "Just plain text"


@pytest.mark.asyncio
async def test_webfetch_unsupported_content():
    mock_resp = MagicMock()
    mock_resp.text = "binary stuff"
    mock_resp.headers = {"content-type": "application/octet-stream"}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cody.core.web.httpx.AsyncClient", return_value=mock_client):
        result = await webfetch("https://example.com/file.bin")

    assert "Unsupported content type" in result


# ── websearch ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_websearch():
    mock_html = """
    <div class="result">
        <a class="result__a" href="https://example.com">Example Title</a>
        <a class="result__snippet">Example description of the result</a>
    </div>
    """
    mock_resp = MagicMock()
    mock_resp.text = mock_html
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cody.core.web.httpx.AsyncClient", return_value=mock_client):
        result = await websearch("test query")

    assert "Search results for: test query" in result
    assert "Example Title" in result


@pytest.mark.asyncio
async def test_websearch_no_results():
    mock_resp = MagicMock()
    mock_resp.text = "<html><body>No results</body></html>"
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("cody.core.web.httpx.AsyncClient", return_value=mock_client):
        result = await websearch("xyznonexistent123")

    assert "No search results found" in result


# ── _parse_ddg_results ───────────────────────────────────────────────────────


def test_parse_ddg_results_basic():
    html = """
    <a class="result__a" href="https://example.com">Title One</a>
    <a class="result__snippet">Snippet one text</a>
    <a class="result__a" href="https://example2.com">Title Two</a>
    <a class="result__snippet">Snippet two text</a>
    """
    results = _parse_ddg_results(html, max_results=10)
    assert len(results) == 2
    assert results[0]["title"] == "Title One"
    assert results[0]["url"] == "https://example.com"
    assert results[0]["snippet"] == "Snippet one text"


def test_parse_ddg_results_max_limit():
    html = """
    <a class="result__a" href="https://a.com">A</a>
    <a class="result__snippet">Snippet A</a>
    <a class="result__a" href="https://b.com">B</a>
    <a class="result__snippet">Snippet B</a>
    <a class="result__a" href="https://c.com">C</a>
    <a class="result__snippet">Snippet C</a>
    """
    results = _parse_ddg_results(html, max_results=2)
    assert len(results) == 2


def test_parse_ddg_results_empty():
    results = _parse_ddg_results("<html></html>", max_results=10)
    assert results == []


def test_parse_ddg_results_uddg_redirect():
    html = """
    <a class="result__a" href="/l/?uddg=https%3A%2F%2Freal.com%2Fpage&rut=abc">Title</a>
    <a class="result__snippet">Snippet</a>
    """
    results = _parse_ddg_results(html, max_results=10)
    assert len(results) == 1
    assert results[0]["url"] == "https://real.com/page"
