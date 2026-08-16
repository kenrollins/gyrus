"""M3 curve harness — agent-driven procedural-reuse loops (journal-026).

The mechanism (outcomes.py + credit assignment) was proven on one real turn;
THE CURVE — tool-success-on-recall climbing as bad procedures lose recall
rank — needs repeated reuse->outcome cycles that organic usage hasn't
generated yet. This drives them honestly (the 2026-08-13 plan: agent-
constructed signal proves the MECHANISM'S dynamics, not organic volume):

  each (round, task):
    1. /v1/prefetch logs recalls for a task-shaped query
    2. the TOP procedural recall's own text is parsed for the command or
       script it references, and a READ-ONLY probe of that claim runs on the
       Pip VM over ssh (--help / test -f / sh -n — never a mutation)
    3. the turn posts back through the real pipeline (extract=false +
       mark-extracted: outcome-scored, never store-polluting)
  between rounds: score_pending + a committed consolidation, so credit moves
  confidence and the next round's ranking feels it.

Genuine outcomes only: a memory referencing a script that no longer exists
FAILS its probe — that stale-advice signal is exactly what the curve needs.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

GYRUS = "http://10.0.13.11:8000"
SSH = ["ssh", "-J", "gb10", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
       "agent@10.0.13.12"]

TASKS = [
    "set skill candidate lifecycle status",
    "capture an episode note for this session",
    "check open loops and pending follow-ups",
    "prune stale sessions and logs maintenance",
    "run the proactive review script",
    "send an email with an attachment via gmail script",
    # Failure-capable tasks: recalls here reference the RETIRED openbrain
    # system and other possibly-stale procedures. If their scripts are gone,
    # the probe genuinely fails — the negative signal the curve needs.
    "scan openbrain promotion candidates",
    "run the openbrain autopromote candidates script",
    "run the episode promotion executor",
    "run the skill candidate lifecycle script",
    # Targets memory 2114 (confidence 1.00): "run python ~/.hermes/scripts/
    # pip_openbrain_autopromote_candidates.py --json --limit 8" — the script
    # is retired on the VM. The store's MOST confident procedural memory
    # giving dead advice is the curve's ideal falsification subject.
    "process openbrain promotion kinds with autopromote json limit",
    "mark openbrain candidate applied after processing",
]

_SCRIPT_PATH = re.compile(r"[`'\"]?(~?/[\w~./-]*\.(?:py|sh))[`'\"]?")
_SCRIPT_BARE = re.compile(r"\b([\w-]+\.(?:py|sh))\b")
_HERMES_CMD = re.compile(r"`(hermes [a-z]+ [a-z]+)`")


def probe_command(fact: str) -> str | None:
    """Derive a safe, read-only probe of the memory's claim. None = no
    concrete command in the fact (turn will carry no tool activity).

    Probe design is about FAIRNESS, learned the hard way in round 1:
    - bash -lc, or a non-login ssh shell's PATH fails commands that work
      fine in real sessions — a harness artifact scored as bad advice;
    - py_compile / sh -n, not --help — an argparse-less script erroring on
      --help is not stale advice. "Exists and parses" is the honest
      read-only proxy for "the referenced procedure is real".
    """
    m = _SCRIPT_PATH.search(fact)
    path = m.group(1) if m else None
    if not path:
        m = _SCRIPT_BARE.search(fact)
        if m:
            path = f"~/.hermes/scripts/{m.group(1)}"
    if path:
        if path.endswith(".py"):
            inner = f"test -f {path} && timeout 20 python3 -m py_compile {path}"
        else:
            inner = f"test -f {path} && sh -n {path}"
        return f"bash -lc '{inner}'"
    m = _HERMES_CMD.search(fact)
    if m:
        return f"bash -lc 'command -v hermes >/dev/null && timeout 20 {m.group(1)} --help'"
    return None


def http(path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        GYRUS + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def run_round(rnd: int) -> list[dict]:
    results = []
    for task in TASKS:
        session = f"m3-drive-r{rnd}"
        q = urllib.parse.quote(task)
        recalled = http(f"/v1/prefetch?session_id={session}&q={q}").get("memories", [])
        proc = next((m for m in recalled if m.get("tier") == "procedural"), None)
        rec = {"round": rnd, "task": task,
               "top_procedural": proc and {"id": proc["id"], "fact": proc["fact"][:120]}}
        if not proc:
            results.append({**rec, "outcome": "no procedural recall"})
            continue
        cmd = probe_command(proc["fact"])
        if not cmd:
            results.append({**rec, "outcome": "no derivable command"})
            continue
        r = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=60)
        ok = r.returncode == 0
        out = (r.stdout + r.stderr)[:800]
        tool_result = json.dumps({"success": ok, "exit_code": r.returncode, "output": out})
        assistant = (f"Following the remembered procedure: {proc['fact'][:300]}\n"
                     f"Applying it — first locating and validating the script/"
                     f"command it references before execution.")
        turn = http("/v1/turns", {
            "session_id": session, "turn_index": rnd * 100 + TASKS.index(task),
            "platform": "m3-harness", "user_text": task, "assistant_text": assistant,
            "extract": False,
            "messages": [
                {"role": "user", "content": task},
                {"role": "assistant", "content": assistant,
                 "tool_calls": [{"function": {"name": "ssh_exec",
                                              "arguments": json.dumps({"command": cmd})}}]},
                {"role": "tool", "content": tool_result},
            ]})
        http("/v1/turns/mark-extracted", {"turn_ids": [turn["id"]]})
        results.append({**rec, "cmd": cmd, "success": ok, "turn_id": turn["id"]})
        time.sleep(1)
    return results


if __name__ == "__main__":
    rnd = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    out = run_round(rnd)
    print(json.dumps(out, indent=1))
    driven = [r for r in out if "success" in r]
    if driven:
        rate = sum(r["success"] for r in driven) / len(driven)
        print(f"\nround {rnd}: {len(driven)} driven, tool-success-on-recall = {rate:.0%}",
              file=sys.stderr)
