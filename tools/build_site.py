#!/usr/bin/env python
"""Assemble the public site from the repository's canonical docs.

The gyrus evolution over its predecessors' sites:

  - gemma-forge published `docs/` wholesale and over-shared (build-log candor,
    self-incriminating nav titles reached the customer-facing site).
  - qaoa-grid-ops split `site_src/` from `docs/` — single-sourced, but curation
    was manual (you chose what to copy).
  - gyrus drives publishing off the `visibility:` frontmatter field. This
    script copies ONLY `visibility: public` journal entries and gotchas, plus
    the design docs meant to be shared. Anything marked `internal`, and the
    whole `fable-review/` / operator-handoff surface, can never reach the site
    — structurally, not by remembering to exclude it.

Generated pages are written under site_src/ and are gitignored; the canonical
copies live in docs/. Drift is impossible by construction.

Run:  python tools/build_site.py   (then `mkdocs build --strict`)
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site_src"
JOURNAL_SRC = ROOT / "docs" / "journal"
ADR_SRC = ROOT / "docs" / "adr"


def frontmatter(text: str) -> tuple[dict, str]:
    """Split a leading YAML block from body. Minimal parser (no yaml dep)."""
    m = re.match(r"\A---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not m:
        return {}, text
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^(\w+):\s*(.*)$", line)
        if km:
            fields[km.group(1)] = km.group(2).strip().strip('"')
    return fields, m.group(2)


def is_public(fm: dict) -> bool:
    # Default-deny: only an explicit visibility: public publishes.
    return fm.get("visibility", "").lower() == "public"


GH_BLOB = "https://github.com/kenrollins/gyrus/blob/main"
_LINK = re.compile(r"\]\(([^)]*\.md[^)]*)\)")

# "Pip" is the private codename for the agent — it means nothing to a public
# reader. Genericize it on the SITE only (the working docs keep "Pip", where it
# reads naturally). Case-sensitive + word-boundary so lowercase identifiers
# (pip-codex, pip_conversation_harvest.py) and ALL-CAPS env vars (PIP_INBOUND)
# are untouched — only the agent's name in prose is replaced.
_PUBLICIZE = [
    (re.compile(r"Pip \(Ken's Hermes agent\)"), "the agent (a Hermes agent)"),
    (re.compile(r"Ken's Hermes agent"), "the Hermes agent"),
    (re.compile(r"\bPip's\b"), "the agent's"),
    (re.compile(r"\bPip\b"), "the agent"),
]


def publicize(text: str) -> str:
    for pat, repl in _PUBLICIZE:
        text = pat.sub(repl, text)
    return text


def rewrite_links(body: str, *, root: str) -> str:
    """Remap repo-relative .md links to the site's layout.

    Journal entries are authored with links relative to docs/journal/ (`../adr/`,
    `../references/SOURCES.md`, `../fable-review/…`). In the site, ADRs live under
    decisions/, SOURCES is sources.md, and the internal surfaces (fable-review,
    tools, handoffs) aren't published at all — those become links to the source
    on GitHub so they still resolve. `root` is the prefix to the site root from
    the current file ("../" for journal/, "../../" for journal/gotchas/).
    """
    def repl(m: re.Match) -> str:
        href = m.group(1)
        base, _, anchor = href.partition("#")
        anchor = ("#" + anchor) if anchor else ""
        fn = base.rsplit("/", 1)[-1]
        if "/adr/" in base and re.match(r"\d{4}-", fn):
            return f"]({root}decisions/{fn}{anchor})"
        if base.endswith("references/SOURCES.md"):
            return f"]({root}sources.md{anchor})"
        if base.endswith("design/ARCHITECTURE.md"):
            return f"]({root}architecture.md{anchor})"
        if re.match(r"\d{4}-\d\d-\d\d-.*\.md$", fn):          # sibling journal entry
            return f"](../{fn}{anchor})" if root == "../../" else f"]({fn}{anchor})"
        if base.lstrip("./").startswith("gotchas/") or "/gotchas/" in base:
            return f"](gotchas/{fn}{anchor})" if root == "../" else f"]({fn}{anchor})"
        # everything else is unpublished → point at the source on GitHub
        repo = re.sub(r"^(\.\./)+", "", base)
        if repo.split("/", 1)[0] in ("adr", "design", "references", "journal", "fable-review"):
            repo = "docs/" + repo
        return f"]({GH_BLOB}/{repo}{anchor})"
    return _LINK.sub(repl, body)


def _clean(dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)


def copy_doc(src: Path, dst: Path, *, title: str | None = None):
    """Copy a canonical doc, stripping any frontmatter (mkdocs shows the H1)."""
    _, body = frontmatter(src.read_text(encoding="utf-8"))
    if title:
        body = f"# {title}\n\n{body}" if not body.lstrip().startswith("#") else body
    dst.write_text(publicize(body), encoding="utf-8")


def build_journal() -> int:
    """Copy public journal entries + gotchas; generate the index."""
    out = SRC / "journal"
    _clean(out)
    (out / "gotchas").mkdir(exist_ok=True)

    entries, gotchas = [], []
    for p in sorted(JOURNAL_SRC.glob("*.md")):
        if p.name in ("STYLE.md", "index.md"):
            continue
        fm, body = frontmatter(p.read_text(encoding="utf-8"))
        if fm.get("type") == "journal" and is_public(fm):
            (out / p.name).write_text(publicize(rewrite_links(body, root="../")), encoding="utf-8")
            entries.append((fm.get("date", p.stem[:10]), publicize(fm.get("title", p.stem)),
                            publicize(fm.get("one_line", "")), p.name))
    for p in sorted((JOURNAL_SRC / "gotchas").glob("*.md")):
        fm, body = frontmatter(p.read_text(encoding="utf-8"))
        if fm.get("type") == "gotcha" and is_public(fm):
            (out / "gotchas" / p.name).write_text(
                publicize(rewrite_links(body, root="../../")), encoding="utf-8")
            gotchas.append((publicize(fm.get("title", p.stem)), publicize(fm.get("one_line", "")),
                            f"gotchas/{p.name}"))

    entries.sort(reverse=True)  # newest first
    lines = ["---", "title: Journal", "---", "", "# The build journal", "",
             "The record of how gyrus was built — decisions, surprises, and the",
             "things that broke — written as the work happened. Only entries",
             "marked public appear here; the working log keeps more.", ""]
    cur = None
    for date, title, one, name in entries:
        if date != cur:
            lines += ["", f"## {date}", ""]
            cur = date
        lines.append(f"- [{title}]({name})" + (f" — {one}" if one else ""))
    if gotchas:
        lines += ["", "## Gotchas", "",
                  "Atomic “X breaks Y because Z” notes, readable on their own.", ""]
        for title, one, rel in sorted(gotchas):
            lines.append(f"- [{title}]({rel})" + (f" — {one}" if one else ""))
    (out / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # awesome-pages ordering: index first, then newest entries, gotchas last.
    order = ["index.md"] + [n for *_, n in entries] + ["gotchas"]
    (out / ".pages").write_text("title: Journal\nnav:\n" +
                                "\n".join(f"  - {n}" for n in order) + "\n")
    print(f"  journal  {len(entries)} entries, {len(gotchas)} gotchas (public only)")
    return len(entries) + len(gotchas)


def build_decisions() -> int:
    """Copy the ADRs — the design decisions, shareable by nature."""
    out = SRC / "decisions"
    _clean(out)
    adrs = sorted(ADR_SRC.glob("[0-9]*.md"))
    for p in adrs:
        copy_doc(p, out / p.name)
    lines = ["---", "title: Decisions", "---", "", "# Architecture decisions", "",
             "The accepted ADRs — why gyrus is shaped the way it is.", ""]
    for p in adrs:
        fm, _ = frontmatter(p.read_text(encoding="utf-8"))
        # ADRs lead with an H1 title line; pull it for the index.
        first_h1 = next((ln[2:] for ln in p.read_text().splitlines()
                         if ln.startswith("# ")), p.stem)
        lines.append(f"- [{first_h1}]({p.name})")
    (out / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / ".pages").write_text("title: Decisions\nnav:\n  - index.md\n" +
                                "\n".join(f"  - {p.name}" for p in adrs) + "\n")
    print(f"  decisions  {len(adrs)} ADRs")
    return len(adrs)


def build_pages():
    """Copy the top-level narrative docs into site pages."""
    copy_doc(ROOT / "BRIEF.md", SRC / "brief.md")
    copy_doc(ROOT / "docs" / "design" / "ARCHITECTURE.md", SRC / "architecture.md")
    copy_doc(ROOT / "docs" / "references" / "SOURCES.md", SRC / "sources.md")
    print("  pages    brief, architecture, sources")


def build_root_nav():
    """Top-level nav order (awesome-pages reads this at site_src root)."""
    (SRC / ".pages").write_text(
        "nav:\n"
        "  - index.md\n"
        "  - The Claim: brief.md\n"
        "  - Architecture: architecture.md\n"
        "  - decisions\n"
        "  - journal\n"
        "  - Sources: sources.md\n"
        "  - About: about.md\n")
    print("  nav      root .pages")


def main():
    print("building gyrus site sources (public-only)")
    build_pages()
    build_decisions()
    n = build_journal()
    build_root_nav()
    print(f"done — {n} journal items published. Now run: mkdocs build --strict")


if __name__ == "__main__":
    main()
