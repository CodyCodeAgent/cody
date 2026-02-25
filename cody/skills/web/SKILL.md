---
name: web
description: Search the web and fetch webpage content using built-in websearch and webfetch tools. Use when researching topics, reading documentation, or finding solutions online.
metadata:
  author: cody
  version: "1.0"
---

# Web Search & Fetch

Search the web and fetch webpage content using Cody's built-in web tools.

## Available Tools

### websearch — Search the web
```
websearch(query="python asyncio tutorial")
```
Uses DuckDuckGo HTML search. Returns titles, URLs, and snippets. No API key required.

### webfetch — Fetch a webpage
```
webfetch(url="https://docs.python.org/3/library/asyncio.html")
```
Fetches the page, converts HTML to Markdown. Also handles JSON and plain text responses.

## Usage Patterns

### Research a topic
1. `websearch("how to implement OAuth 2.0 in FastAPI")` — find relevant pages
2. `webfetch("https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/")` — read the documentation

### Check API documentation
```
webfetch("https://api.example.com/docs")
```

### Find error solutions
```
websearch("Python RuntimeError: Event loop is closed fix")
```

### Get latest package info
```
webfetch("https://pypi.org/pypi/pydantic/json")
```

## Notes

- `websearch` uses DuckDuckGo — no API key needed
- `webfetch` converts HTML to clean Markdown for readability
- `webfetch` supports JSON responses (returns formatted JSON)
- Large pages are automatically truncated to fit context limits
- Respect robots.txt and rate limits when fetching multiple pages
