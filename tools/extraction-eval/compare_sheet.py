#!/usr/bin/env python3
"""Build ONE side-by-side grading sheet from several bench_lanes.py result files.

Why (2026-10-19, GB10 Super VL bake-off). bench_lanes.py writes its grading
sheet to goldens/LANE-BENCH-SHEET.md and each run OVERWRITES the last, so
three runs of one lane each (incumbent / candidate thinking-off / candidate
medium-thinking) left exactly one sheet — the last run's, with 0 facts. The
facts themselves survive in each run's --out JSON. This stitches those JSONs
back into the LANE-BENCH-SHEET.md shape: per window, each engine's facts
with KEEP / DROP / WRONG-TIER boxes, then a MISSED section.

Usage:
  compare_sheet.py --out SHEET.md LABEL=res-a.json LABEL=res-b.json ...

LABEL is the heading shown for that file (the JSON's own lane names are the
throwaway bake-off lane ids). A file holding several lanes gets LABEL/lane.

Run it with `python3 -I` from outside the results directory — the inputs are
private conversation content, and the sheet it writes is too. Keep both in a
gitignored location (goldens/ is).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def load(spec: str) -> list[tuple[str, dict]]:
    label, _, path = spec.rpartition("=")
    p = pathlib.Path(path)
    doc = json.loads(p.read_text())
    label = label or p.stem
    lanes = doc.get("results", {})
    if len(lanes) == 1:
        return [(label, next(iter(lanes.values())))]
    return [(f"{label}/{lane}", res) for lane, res in lanes.items()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Lane bench — side by side")
    ap.add_argument("specs", nargs="+", metavar="LABEL=res.json")
    a = ap.parse_args()

    engines: list[tuple[str, dict]] = []
    versions = set()
    for s in a.specs:
        doc = json.loads(pathlib.Path(s.rpartition("=")[2]).read_text())
        versions.add(doc.get("prompt_version", "?"))
        engines += load(s)
    windows = sorted({w for _, res in engines for w in res})

    sheet = [f"# {a.title} — prompt {', '.join(sorted(versions))}", "",
             "Mark each fact KEEP / DROP / WRONG-TIER (tick ONE box per fact; leave",
             "the other two empty). A lane is only a candidate if its KEEP set covers",
             "the baseline's. Boxes: `[K] [D] [W]` — put an x in the one that applies.", "",
             "Engines graded:"]
    sheet += [f"- **{lab}**" for lab, _ in engines]
    sheet.append("")
    for w in windows:
        sheet.append(f"## window: {w}")
        for lab, res in engines:
            r = res.get(w)
            if r is None:
                sheet += [f"### {lab} — (not run)", ""]
                continue
            head = (f"{r['n']} facts, {r['seconds']}s" if r.get("ok")
                    else f"FAILED after {r.get('seconds')}s: {r.get('error', '')}")
            sheet.append(f"### {lab} — {head}")
            facts = r.get("facts") or []
            sheet += [f"- K[ ] D[ ] W[ ] [{f['tier']:10s}|{f['provenance']:8s}] {f['fact']}"
                      for f in facts] or ["- (nothing extracted)"]
            sheet.append("")
        sheet += ["**MISSED (facts in the window that no engine extracted — one per line):**",
                  "", "- ", "", "---", ""]
    out = pathlib.Path(a.out)
    out.write_text("\n".join(sheet))
    n = sum(len((r or {}).get("facts") or []) for _, res in engines for r in res.values())
    print(f"wrote {out}: {len(windows)} windows, {len(engines)} engines, {n} facts to grade")
    return 0


if __name__ == "__main__":
    sys.exit(main())
