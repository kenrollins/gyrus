#!/usr/bin/env python
"""Fail the build if any internal link in the generated site 404s.

`mkdocs --strict` validates links written in MARKDOWN, but not root-absolute or
raw-HTML links passed through the config (the footer disclaimer link, for one).
This walks the built site/ and confirms every internal href resolves to a file.

Run after `mkdocs build`:  python tools/check_links.py [site_dir]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP = ("http://", "https://", "mailto:", "javascript:", "data:", "//", "#")


def _base_path() -> str:
    cfg = (Path(__file__).resolve().parents[1] / "mkdocs.yml").read_text()
    m = re.search(r"^site_url:\s*(\S+)", cfg, re.M)
    if not m:
        return "/"
    path = re.sub(r"^https?://[^/]+", "", m.group(1).strip())
    return path if path.endswith("/") else path + "/"


def main() -> int:
    site = Path(sys.argv[1] if len(sys.argv) > 1 else "site").resolve()
    base = _base_path()
    broken: list[str] = []
    href_re = re.compile(r'(?:href|src)="([^"]+)"')

    for html in site.rglob("*.html"):
        for raw in href_re.findall(html.read_text(encoding="utf-8", errors="ignore")):
            href = raw.split("#")[0].split("?")[0]
            if not href or href.startswith(SKIP):
                continue
            if href.startswith("/"):
                rel = href[len(base):] if href.startswith(base) else href.lstrip("/")
                target = site / rel
            else:
                target = (html.parent / href).resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                broken.append(f"{html.relative_to(site)} -> {raw}")

    if broken:
        print(f"BROKEN internal links ({len(broken)}):", file=sys.stderr)
        for b in sorted(set(broken)):
            print("  " + b, file=sys.stderr)
        return 1
    print("internal links OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
