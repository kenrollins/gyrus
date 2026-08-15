"""Does the union second pass earn its cost?

gpt-oss:120b runs on EVERY extraction as a second pass. Its justification is
one window, measured once: "the 70B returns DOMAIN insights, gpt-oss returns
the REFERENCE layer". This asks the decision question instead: of gpt-oss's
facts, how many SURVIVE production's own dedupe against the 70B's? Anything
that dedupes away is cost with no memory behind it.

Uses the real rule from extraction.persist: exact normalized hash, then
cosine >= settings.dedupe_threshold on gateway embeddings.
"""
import asyncio, json, sys
sys.path.insert(0, "/usr/local/lib/python3.12/site-packages")
from gyrus import gateway
from gyrus.config import settings
from gyrus.extraction import Fact

def norm(s): return " ".join(s.lower().split())

async def main():
    d = json.load(open("/tmp/eval/goldens/results/bench-120b.json"))
    r = d["results"]
    A, B = "kaiju/nemotron:70b", "kaiju/gpt-oss:120b"
    tot_new = tot_dup = tot_b = 0
    per_window = []
    for w in r[A]:
        fa = [f for f in r[A][w]["facts"]]
        fb = [f for f in r[B][w]["facts"]]
        if not fb:
            per_window.append((w, len(fa), 0, 0, [])); continue
        ha = {norm(f["fact"]) for f in fa}
        cand = [f for f in fb if norm(f["fact"]) not in ha]
        exact_dups = len(fb) - len(cand)
        uniq = []
        if cand and fa:
            va = await gateway.embed([f["fact"] for f in fa])
            vb = await gateway.embed([f["fact"] for f in cand])
            def cos(x, y):
                dot = sum(p*q for p, q in zip(x, y))
                na = sum(p*p for p in x) ** .5; nb = sum(q*q for q in y) ** .5
                return dot/(na*nb) if na and nb else 0.0
            for f, vv in zip(cand, vb):
                if vv is None: uniq.append(f); continue
                best = max((cos(vv, u) for u in va if u), default=0.0)
                if best < settings.dedupe_threshold: uniq.append(f)
        elif cand:
            uniq = cand
        tot_new += len(uniq); tot_dup += len(fb) - len(uniq); tot_b += len(fb)
        per_window.append((w, len(fa), len(fb), len(uniq), uniq))
    print(f"dedupe_threshold = {settings.dedupe_threshold}\n")
    print(f"{'window':22s} {'70B':>4s} {'gpt-oss':>8s} {'survives':>9s}")
    for w, a, b, u, _ in per_window:
        print(f"{w:22s} {a:>4d} {b:>8d} {u:>9d}")
    print(f"\n{'TOTAL':22s} {sum(p[1] for p in per_window):>4d} {tot_b:>8d} {tot_new:>9d}")
    print(f"\ngpt-oss facts absorbed by dedupe: {tot_dup}/{tot_b} "
          f"({100*tot_dup/max(1,tot_b):.0f}%)")
    print(f"unique contribution: {tot_new} facts across 6 windows\n")
    print("=== what actually survives (the union's whole value) ===")
    for w, a, b, u, facts in per_window:
        for f in facts[:4]:
            print(f"  [{w[:18]:19s}] {f['tier']:10s}|{f['provenance']:8s} {f['fact'][:88]}")
asyncio.run(main())
