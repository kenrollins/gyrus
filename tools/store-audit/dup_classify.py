"""Classify dup_scan.py's pairs by the mechanism that let them exist.

Any same-tier pair at >= dedupe_threshold today implies that when its LATER
member was inserted, one of these was true:

  A. the row predates migration 0003, when the dedupe check ran through an
     ivfflat index with ~28% recall — the check was effectively blind;
  B. the pair shares a created_at (same transaction = same persist call):
     in-call facts ARE visible to each other's check when embedded, so a
     same-txn pair means the whole batch had no vectors (#9 by construction);
  C1. small gap, different txns: a concurrent-window race (uncommitted rows
     are invisible across transactions) or the earlier twin still awaiting
     its vector from _embed_sweeper (#9 one step removed);
  C2. large gap after the exact-scan era: the later insert skipped its check —
     the embed-failure path (#9) with its twin long since embedded.

Zero same-source_key pairs is the check that migration 0006's independence
rule is holding.

    docker cp tools/store-audit/dup_classify.py gyrus:/tmp/dup_classify.py
    docker exec gyrus python /tmp/dup_classify.py

Measured 2026-08-15: A=177 (95%), B=0, C1=3, C2=7; same-source_key=0.
The C cluster traces to one embed outage (turn 823, 03:01:52). journal-021.
"""
import json
from datetime import datetime, timedelta, timezone

PAIRS = "/tmp/dup_pairs.json"
THRESHOLD = 0.93
STORE_ROWS = 12886          # denominator for the headline %; update per run
# migration 0003 (drop ivfflat) committed 2026-08-13 11:14; +buffer for the
# container rebuild that actually applied it.
EXACT_ERA = datetime(2026, 8, 13, 11, 30, tzinfo=timezone.utc)


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def main() -> None:
    pairs = json.load(open(PAIRS))
    off = [p for p in pairs if p["sim"] >= THRESHOLD]
    print(f"pairs >=0.90: {len(pairs)}   offending (>={THRESHOLD}): {len(off)}"
          f"  ({len(off) / STORE_ROWS:.1%} of live store)")

    buckets: dict[str, list] = {
        "A_blind_index_era": [], "B_same_txn_no_vector": [],
        "C1_close_race_or_sweeper": [], "C2_late_skip": []}
    for p in off:
        if ts(p["created"]) < EXACT_ERA:
            buckets["A_blind_index_era"].append(p)
        elif p["created"] == p["nn_created"]:
            buckets["B_same_txn_no_vector"].append(p)
        elif ts(p["created"]) - ts(p["nn_created"]) <= timedelta(minutes=10):
            buckets["C1_close_race_or_sweeper"].append(p)
        else:
            buckets["C2_late_skip"].append(p)

    for k, v in buckets.items():
        same_key = sum(1 for p in v if p["skey"] and p["skey"] == p["nn_skey"])
        by_src: dict[str, int] = {}
        days: dict[str, int] = {}
        for p in v:
            by_src[p["stype"] or "(personal)"] = by_src.get(p["stype"] or "(personal)", 0) + 1
            days[p["created"][:13]] = days.get(p["created"][:13], 0) + 1
        print(f"\n{k}: {len(v)}  ({len(v) / max(len(off), 1):.0%} of offending)"
              f"  same-source_key: {same_key}")
        print("  by source:", dict(sorted(by_src.items(), key=lambda x: -x[1])))
        print("  top created-hours:", sorted(days.items(), key=lambda x: -x[1])[:6])

    print("\n== highest-sim examples per bucket ==")
    for k, v in buckets.items():
        for p in sorted(v, key=lambda p: -p["sim"])[:3]:
            dt = ts(p["created"]) - ts(p["nn_created"])
            print(f"  {k}: {p['id']}~{p['nn_id']} sim={p['sim']:.3f} dt={dt}"
                  f" src={p['stype']} ref={str(p['sref'])[:60]}")


if __name__ == "__main__":
    main()
