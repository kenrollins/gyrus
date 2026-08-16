"""Band discriminator — adjudicate 0.90-0.93 near-dup pairs (journal-023).

The graded sample showed the band is ~80% same-claim rewordings (should fold
as corroboration) and ~20% genuinely distinct facts differing by one critical
token — which cosine cannot see. So: no threshold move; adjudicate each pair.

Two stages, cheapest first:
  1. DETERMINISTIC: if the two facts differ in any digit-bearing token or
     code-identifier token (paths, flags, ids, link classes), they are
     DISTINCT. This alone clears most of the graded distinct pairs
     (ADR-0024 vs ADR-0018, `pip install .` vs `.[test]`).
  2. LLM (lab/flash): remaining pairs get a same-claim judgment. Flash is
     enough — the question is "same claim or not", not extraction.

Verdicts: distinct | same | unsure. Only "same" is foldable, and the caller
decides whether to commit. Run validate() against the hand-graded pairs
before trusting a changed heuristic.
"""
from __future__ import annotations

import re

# A token that carries exact meaning: digits, dotted/underscored/bracketed
# identifiers, paths, flags. Lowercased comparison; possessives stripped.
_IDENT = re.compile(r"[a-z0-9_./\[\]-]*(?:\d|_|\.|\[|/)[a-z0-9_./\[\]:-]*", re.I)
_WORD = re.compile(r"[a-z0-9_./\[\]:-]+", re.I)


_CAMEL = re.compile(r"[a-z]+[A-Z][A-Za-z]*")


def _critical_tokens(text: str) -> set[str]:
    """Tokens that carry exact meaning. Classified BEFORE lowercasing —
    camelCase (notePath, onFileExists) is an identifier signature that
    vanishes under .lower(), which round-2 validation caught the hard way."""
    toks = set()
    for w in re.findall(r"[A-Za-z0-9_./\[\]:-]+", text):
        w = w.strip(".,;:")
        if not w:
            continue
        if any(c.isdigit() for c in w) or _IDENT.fullmatch(w) or _CAMEL.fullmatch(w):
            toks.add(w.lower())
    return toks


def deterministic_verdict(fact_a: str, fact_b: str) -> str | None:
    """'distinct' only on a CONFLICTING SUBSTITUTION; None = can't tell.

    First validation run (30 hand-graded pairs) proved symmetric-difference
    alone is wrong: a fact that merely mentions an extra token ("report
    (2026)", a trailing DOI, a reworded flag) is a superset of the same
    claim, not a different claim. The distinct signature is exclusive
    critical tokens on BOTH sides — ADR-0024 vs ADR-0018, foam-note-link vs
    foam-placeholder-link — a slot filled with conflicting values. Supersets
    and no-identifier pairs fall through to the LLM.
    """
    a, b = _critical_tokens(fact_a), _critical_tokens(fact_b)
    only_a, only_b = a - b, b - a
    if only_a and only_b:
        return "distinct"
    # Enumeration-loss guard (validation round 2): a fold keeps ONE member,
    # so a fact whose exclusive content is a sizable identifier list ("has
    # settings: notePath, templatePath, title, ...") cannot be folded into
    # its poorer twin without losing the list — even when a judge calls the
    # pair "the same claim". Reference-layer enumerations are exactly what
    # this store exists to keep findable.
    if len(only_a) >= 3 or len(only_b) >= 3:
        return "distinct"
    return None


LLM_SYSTEM = """You maintain a memory store that must not hoard duplicates but must \
never merge two facts that differ in substance. For each pair, judge: if the store \
kept only ONE of the two statements, would anything of substance be lost?

"same" — nothing lost: rewordings, reorderings, or one statement being a more/less \
detailed version of the SAME assertion. Extra detail, a citation, or a softer phrasing \
does NOT make claims different.
  A: "The DOE blueprint report (2026) has DOI 10.2172/3022533."
  B: "DOE published a blueprint for quantum supercomputing with DOI 10.2172/3022533"
  -> same (one assertion, one wordier)
  A: "Set updates.backup_keep to 3."   B: "updates.backup_keep set to 3"  -> same

"different" — something lost: the statements fill the same sentence-shape with \
CONFLICTING or COMPLEMENTARY substance — a different object, value, command, person, \
or consequence. However similar the wording, both must be kept.
  A: "Use cmd+N to create a new file"   B: "Use cmd+S to save the file" -> different
  A: "The fix is to enable ACPI in the config"
  B: "The cause is the provider not setting ACPI by default" -> different (fix vs cause)

"unsure" — genuinely cannot tell from the text alone.
Answer ONLY a JSON array: [{"id": "<id>", "verdict": "same"|"different"|"unsure"}]"""


def llm_batch_prompt(pairs: list[dict]) -> str:
    lines = []
    for p in pairs:
        lines.append(f'{p["pair_id"]}:\nA: {p["fact_a"]}\nB: {p["fact_b"]}\n')
    return "Pairs:\n\n" + "\n".join(lines)
