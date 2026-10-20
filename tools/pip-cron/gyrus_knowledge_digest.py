#!/usr/bin/env python3
"""Weekly gyrus knowledge digest — Pip cron, --no-agent (stdout is the post).

Ken 2026-10-20: instead of a browse UI nobody opens, the ten highest-authority
knowledge items gyrus gleaned this week, one line each, in Zulip. Reading this
IS demand (ADR-0008): the ten shown get a browse bump server-side. Empty
stdout = nothing posted.
"""
import json
import os
import pathlib
import urllib.parse
import urllib.request

BASE = os.environ.get("GYRUS_BASE_URL", "http://10.0.13.11:8000")
env = pathlib.Path.home() / ".hermes" / ".env"
TOKEN = os.environ.get("GYRUS_API_TOKEN", "")
if not TOKEN and env.exists():
    for line in env.read_text().splitlines():
        if line.startswith("GYRUS_API_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip().strip('"')

q = urllib.parse.urlencode({"days": 7, "limit": 10, "order": "confidence"})
req = urllib.request.Request(f"{BASE}/v1/insights?{q}",
                             headers={"Authorization": f"Bearer {TOKEN}"})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
except Exception as e:  # noqa: BLE001
    print(f"gyrus digest: could not reach gyrus ({e})")
    raise SystemExit(0)

items = d.get("insights") or []
if not items:
    raise SystemExit(0)
by_src = d.get("by_source") or {}
print("**gyrus — what the lab learned this week** (top 10 by confidence, 7 days)")
for it in items:
    src = it.get("source_type") or "?"
    conf = float(it.get("confidence") or 0)
    ref = (it.get("source_ref") or "")[:60]
    print(f"- `{src}` {conf:.2f} — {it['fact'][:220]}" + (f"  _({ref})_" if ref else ""))
print(f"\n_store: {', '.join(f'{k} {v}' for k, v in sorted(by_src.items(), key=lambda kv: -kv[1]))}_")
print("_reply with the id of anything wrong and Pip will retire it; silence for a month means this digest goes too._")
