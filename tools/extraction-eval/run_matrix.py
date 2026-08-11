#!/usr/bin/env python3
"""Run the extraction matrix: every goldens/*.json window x every model config.

Results land in goldens/results/<window>--<config>.json (goldens/ is
gitignored — extracted facts can carry personal content). Also emits
goldens/GRADING-SHEET.md for the human answer-key pass.

Usage: GYRUS_KEY=... python3 run_matrix.py [configs: model[:v01] ...]
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).parent
GOLD = HERE / "goldens"
RES = GOLD / "results"
RES.mkdir(exist_ok=True)

DEFAULT_CONFIGS = [
    "kaiju/nemotron:70b:v01",
    "vllm/nemotron-lightning:v01",
    "vllm/qwen-35b:v01",
]


def run_one(window: pathlib.Path, config: str) -> dict:
    parts = config.rsplit(":", 1)
    model, v01 = (parts[0], True) if parts[-1] == "v01" else (config, False)
    cmd = [sys.executable, str(HERE / "extract_dryrun.py"), str(window), model]
    if v01:
        cmd.append("--v01")
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return {
        "window": window.stem, "config": config, "seconds": round(time.time() - t0, 1),
        "ok": p.returncode == 0, "stdout": p.stdout, "stderr": p.stderr[-500:],
    }


def parse_facts(stdout: str) -> list[str]:
    return [ln.strip() for ln in stdout.splitlines() if ln.strip().startswith("[")]


def main() -> None:
    configs = sys.argv[1:] or DEFAULT_CONFIGS
    windows = sorted(GOLD.glob("*.json"))
    sheet = ["# Extraction golden-set grading sheet", "",
             "For each fact: mark KEEP / DROP / WRONG-TIER. Add any MISSED facts",
             "per window at the bottom of its section. This becomes the answer key.", ""]
    for w in windows:
        sheet.append(f"## window: {w.stem}")
        for cfg in configs:
            r = run_one(w, cfg)
            (RES / f"{w.stem}--{cfg.replace('/', '_').replace(':', '_')}.json").write_text(json.dumps(r, indent=1))
            facts = parse_facts(r["stdout"]) if r["ok"] else []
            status = f"{len(facts)} facts, {r['seconds']}s" if r["ok"] else f"FAILED: {r['stderr'][:120]}"
            print(f"{w.stem:24s} | {cfg:32s} | {status}")
            sheet.append(f"### {cfg} — {status}")
            sheet += [f"- [ ] {f}" for f in facts] or (["- (nothing extracted)"] if r["ok"] else ["- (run failed)"])
            sheet.append("")
        sheet.append("**MISSED (add here):**\n\n---\n")
    (GOLD / "GRADING-SHEET.md").write_text("\n".join(sheet))
    print(f"\nwrote {GOLD / 'GRADING-SHEET.md'}")


if __name__ == "__main__":
    main()
