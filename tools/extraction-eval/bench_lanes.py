#!/usr/bin/env python3
"""Benchmark extraction lanes through the PRODUCTION code path.

Why this exists (2026-08-15). `extraction.py` has said since M1 that "the
flash tier extracted almost nothing", and that sentence is why gyrus runs its
heaviest workload on its slowest lane (kaiju/nemotron:70b, 8.5 tok/s, 65s p50
— the slowest thing gyrus calls, measured from LiteLLM's ledger). Re-reading
the run behind the claim, not one of its six windows is a clean measurement:

  conference-cleanup   HTTP failure, 0.2s   — never reached a model
  day3-summaries       HTTP failure, 0.3s   — never reached a model
  cron-quantum-radar   empty response       — the thinking-budget failure the
                                              lab measured on 3 of 5 prompts
  recent-other         content was the string
                       "[ERROR: Agent failed ... API returned None]"
  cron-monday-brief    0 facts              — CORRECT; the 70B also got 0
                                              (a cron window must yield none)
  nqisrc-panel         1 fact in 5.6s       — the only real datapoint

The cause is now confirmed: that run addressed `vllm/nemotron-lightning`,
which this key gets a 403 on. The lane it meant to test is
`vllm/nemotron-lightning-l4`, which answers in 0.1s.

So the claim is unproven, not wrong — and it needs re-testing against the
CURRENT prompt (v1.2, four revisions on from the v0.1 used then).

WHAT MAKES THIS HARNESS DIFFERENT from extract_dryrun.py, which it replaces
for lane comparison:

  - It calls `extraction.extract()`, so it uses the real SYSTEM prompt and
    the real fence/balanced-brace salvage parser. extract_dryrun.py carries
    its own frozen copy of the v0 prompt and a plain `\\[.*\\]` regex, so a
    model emitting almost-JSON scored zero there and fine in production —
    "MALFORMED JSON" in the old results is a parser artifact, not a verdict.
  - It DISABLES the fallback model. chat_json falls back to
    extract_fallback_model on failure, so a lane that fails would have been
    silently answered by nemotron-120b and scored as if it had succeeded.
  - It warms each lane first. kaiju is on-demand and a cold load is ~50s,
    which would otherwise land entirely on whichever lane ran first.

Usage (inside the container, which has the package and the gateway key):
  docker cp tools/extraction-eval gyrus:/tmp/eval
  docker exec gyrus python /tmp/eval/bench_lanes.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import time

sys.path.insert(0, "/usr/local/lib/python3.12/site-packages")

from gyrus import extraction, gateway            # noqa: E402
from gyrus.config import settings                # noqa: E402

LANES = [
    "kaiju/nemotron:70b",          # incumbent workhorse — the baseline
    "vllm/nemotron-lightning-l4",  # the fast lane, scoped and never used
    "lab/flash",                   # same class, thinking pinned off
]


async def warm(model: str) -> float:
    """Cold-load cost, paid once and reported rather than charged to window 1."""
    t0 = time.time()
    try:
        # Budget generously even for a warm-up: a thinking model at
        # max_tokens=64 spends the whole allowance reasoning and returns
        # empty, which now (correctly) raises — a harness artifact, not a
        # property of the lane.
        await gateway.chat_json("Reply with a JSON array.", "Return []", model=model,
                                max_tokens=1024)
    except Exception as e:                                       # noqa: BLE001
        print(f"  warm {model}: {type(e).__name__}: {str(e)[:80]}", flush=True)
    return time.time() - t0


async def run_window(model: str, w: dict, max_tokens: int | None = None,
                     timeout: float | None = None,
                     template_kwargs: dict | None = None) -> dict:
    t0 = time.time()
    try:
        facts = await extraction.extract(w["messages"], model=model,
                                         max_tokens=max_tokens, timeout=timeout,
                                         template_kwargs=template_kwargs)
        return {"ok": True, "seconds": round(time.time() - t0, 1),
                "n": len(facts),
                "facts": [{"tier": f.tier, "provenance": f.provenance,
                           "fact": f.fact, "entities": f.entities} for f in facts]}
    except Exception as e:                                       # noqa: BLE001
        # With the fallback disabled, a lane failure is visible instead of
        # being answered by another model and scored as a success.
        return {"ok": False, "seconds": round(time.time() - t0, 1), "n": 0,
                "error": f"{type(e).__name__}: {str(e)[:160]}", "facts": []}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goldens", default=str(pathlib.Path(__file__).parent / "goldens"))
    ap.add_argument("--models", nargs="*", default=LANES)
    ap.add_argument("--out", default="")
    ap.add_argument("--max-tokens", type=int, default=0,
                    help="override the completion budget. A THINKING model reasons "
                         "before it writes, so the default measures its budget, not "
                         "its extraction (ADR-0010).")
    ap.add_argument("--timeout", type=float, default=0,
                    help="override chat_json's 300s ceiling. A lane slower than the "
                         "ceiling scores as a quality failure when it is a clock "
                         "failure: at a measured 16 tok/s, vllm/nemotron-120b needs "
                         "~500s to spend an 8000-token budget and cannot finish "
                         "inside 300s at all.")
    ap.add_argument("--no-think", action="store_true",
                    help="send chat_template_kwargs={'enable_thinking': false}. The "
                         "gateway pins this on the flash lanes but NOT on "
                         "vllm/nemotron-120b, so that lane has only ever been "
                         "measured with thinking on — against a task whose output "
                         "is a JSON array.")
    args = ap.parse_args()

    gold_dir = pathlib.Path(args.goldens)
    windows = sorted(p for p in gold_dir.glob("*.json"))
    if not windows:
        print(f"no golden windows in {gold_dir}", file=sys.stderr)
        return 1

    # A lane must answer for itself: no silent substitution.
    settings.extract_fallback_model = ""

    print(f"{len(windows)} windows x {len(args.models)} lanes "
          f"(prompt {extraction.PROMPT_VERSION}, fallback disabled, "
          f"max_tokens={args.max_tokens or 'default 4000'}, "
          f"timeout={args.timeout or 'default 300'}s)\n", flush=True)

    print("warming lanes (kaiju is on-demand; a cold load is ~50s)...", flush=True)
    for m in args.models:
        print(f"  {m:30s} {await warm(m):5.1f}s", flush=True)
    print(flush=True)

    results: dict[str, dict] = {}
    for m in args.models:
        results[m] = {}
        for wp in windows:
            w = json.loads(wp.read_text())
            r = await run_window(m, w, args.max_tokens, args.timeout or None,
                                 {"enable_thinking": False} if args.no_think else None)
            results[m][wp.stem] = r
            status = (f"{r['n']:2d} facts" if r["ok"] else f"FAILED {r.get('error','')[:60]}")
            print(f"  {m:30s} {wp.stem:20s} {r['seconds']:6.1f}s  {status}", flush=True)
        print(flush=True)

    # ---- summary -------------------------------------------------------
    base = args.models[0]
    print(f"{'lane':32s} {'windows ok':>11s} {'facts':>7s} {'total s':>9s} {'vs base':>9s}")
    for m in args.models:
        rs = list(results[m].values())
        ok = sum(1 for r in rs if r["ok"])
        n = sum(r["n"] for r in rs)
        secs = sum(r["seconds"] for r in rs)
        base_secs = sum(r["seconds"] for r in results[base].values()) or 1
        print(f"{m:32s} {ok:>4d}/{len(rs):<6d} {n:>7d} {secs:>9.1f} "
              f"{base_secs / (secs or 1):>8.1f}x")

    out = pathlib.Path(args.out) if args.out else gold_dir / "results" / "lane-bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"prompt_version": extraction.PROMPT_VERSION, "results": results}, indent=1))
    print(f"\nwrote {out}")

    # Grading sheet: facts are the product, so the verdict is a human read of
    # them, not the counts above. Counts say "fast"; only this says "as good".
    sheet = [f"# Lane bench — prompt {extraction.PROMPT_VERSION}", "",
             "Mark each fact KEEP / DROP / WRONG-TIER. A lane is only a",
             "candidate if its KEEP set covers the baseline's.", ""]
    for wp in windows:
        sheet.append(f"## window: {wp.stem}")
        for m in args.models:
            r = results[m][wp.stem]
            head = f"{r['n']} facts, {r['seconds']}s" if r["ok"] else f"FAILED: {r.get('error','')}"
            sheet.append(f"### {m} — {head}")
            sheet += [f"- [ ] [{f['tier']:10s}|{f['provenance']:8s}] {f['fact']}"
                      for f in r["facts"]] or ["- (nothing extracted)"]
            sheet.append("")
        sheet.append("**MISSED (add here):**\n\n---\n")
    (gold_dir / "LANE-BENCH-SHEET.md").write_text("\n".join(sheet))
    print(f"wrote {gold_dir / 'LANE-BENCH-SHEET.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
