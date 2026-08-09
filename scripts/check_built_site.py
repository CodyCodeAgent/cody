#!/usr/bin/env python3
"""Check generated documentation links and assets without network access."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.targets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id") or values.get("name")
        if element_id:
            self.ids.add(element_id)
        target = values.get("href") if tag in {"a", "link"} else values.get("src")
        if target:
            self.targets.append(target)


def normalized_target(root: Path, source: Path, raw_path: str) -> Path:
    path = unquote(raw_path)
    if path.startswith("/cody/"):
        target = root / path.removeprefix("/cody/")
    elif path.startswith("/"):
        target = root / path.removeprefix("/")
    else:
        target = source.parent / path
    if path.endswith("/"):
        target /= "index.html"
    return target.resolve()


def check(site_dir: Path) -> list[str]:
    pages = sorted(site_dir.rglob("*.html"))
    parsed: dict[Path, PageParser] = {}
    errors: list[str] = []

    for page in pages:
        text = page.read_text(encoding="utf-8")
        parser = PageParser()
        parser.feed(text)
        parsed[page.resolve()] = parser
        if SECRET_RE.search(text):
            errors.append(f"{page.relative_to(site_dir)}: possible persisted API key")

    for page, parser in parsed.items():
        for raw_target in parser.targets:
            parts = urlsplit(raw_target)
            if parts.scheme or parts.netloc or raw_target.startswith(("mailto:", "tel:", "data:")):
                continue
            if not parts.path:
                target = page
            else:
                target = normalized_target(site_dir, page, parts.path)
            if not target.exists():
                errors.append(
                    f"{page.relative_to(site_dir)}: missing target `{raw_target}`"
                )
                continue
            if parts.fragment and target.suffix == ".html":
                target_parser = parsed.get(target)
                if target_parser is not None and unquote(parts.fragment) not in target_parser.ids:
                    errors.append(
                        f"{page.relative_to(site_dir)}: missing fragment `{raw_target}`"
                    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site_dir", type=Path)
    args = parser.parse_args()
    site_dir = args.site_dir.resolve()
    errors = check(site_dir)
    if errors:
        print("Built-site checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Built-site checks passed ({len(list(site_dir.rglob('*.html')))} HTML pages).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
