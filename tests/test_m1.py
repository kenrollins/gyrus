"""M1 unit tests — pure logic only (no DB, no gateway, no network).

Every case here is a bug that actually happened during the 2026-08-12 build
and cost real memories. They are regression tests, not coverage theatre.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gyrus import extraction, retrieval          # noqa: E402
from gyrus.gateway import salvage_objects        # noqa: E402


# --- gateway: tolerant JSON ------------------------------------------------

def test_salvage_plain_array():
    assert salvage_objects('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_salvage_recovers_from_missing_comma():
    """The 70B's real failure shape: a delimiter error mid-array."""
    text = '[{"tier":"factual","fact":"first"} {"tier":"factual","fact":"second"}]'
    assert [g["fact"] for g in salvage_objects(text)] == ["first", "second"]


def test_salvage_keeps_what_it_can_past_an_unescaped_quote():
    """An unescaped quote corrupts the remainder, but earlier facts survive.

    Whole-array parsing returned NOTHING here — one bad character discarded a
    whole conference window's extractions. Partial recovery is the point.
    """
    text = '[{"tier":"factual","fact":"good one"}, {"tier":"factual","fact":"bad " quote"}]'
    got = salvage_objects(text)
    assert [g["fact"] for g in got] == ["good one"]


def test_salvage_ignores_prose_and_fences():
    text = 'Here you go:\n```json\n[{"fact": "x"}]\n```\nHope that helps!'
    assert salvage_objects(text) == [{"fact": "x"}]


def test_salvage_handles_braces_inside_strings():
    assert salvage_objects('[{"fact": "use {curly} braces"}]') == [{"fact": "use {curly} braces"}]


def test_salvage_empty_array():
    assert salvage_objects("[]") == []


# --- extraction: validation ------------------------------------------------

def test_clean_drops_bad_tier_and_short_facts():
    raw = [{"tier": "nonsense", "fact": "a long enough fact here"},
           {"tier": "factual", "fact": "short"},
           {"tier": "factual", "fact": "a genuinely durable fact"}]
    got = extraction._clean(raw)
    assert [f.fact for f in got] == ["a genuinely durable fact"]


def test_clean_defaults_unknown_provenance_but_keeps_relayed():
    raw = [{"tier": "factual", "fact": "speaker claimed something", "provenance": "relayed"},
           {"tier": "factual", "fact": "another durable fact", "provenance": "invented"}]
    got = extraction._clean(raw)
    assert [f.provenance for f in got] == ["relayed", "observed"]


def test_clean_dedupes_within_a_window():
    raw = [{"tier": "factual", "fact": "The panel was moderated by Jenks"},
           {"tier": "factual", "fact": "the  panel   was moderated by jenks"}]
    assert len(extraction._clean(raw)) == 1


def test_fact_hash_is_whitespace_and_case_stable():
    a = extraction.Fact("factual", "Ken uses Obsidian", [], "ken_said")
    b = extraction.Fact("factual", "ken   uses obsidian", [], "observed")
    assert a.hash == b.hash


def test_render_window_respects_budget():
    msgs = [{"role": "user", "content": "x" * 50_000}]
    out = extraction.render_window(msgs, char_budget=1000)
    assert len(out) < 1200 and "TRUNCATED" in out


# --- retrieval: query construction ----------------------------------------

def test_or_query_uses_or_semantics():
    """websearch_to_tsquery ANDs by default; a long question then matched nothing."""
    q = retrieval._or_query("how do I like my end of day summaries formatted")
    assert " or " in q
    assert "summaries" in q and "formatted" in q
    assert "do" not in q.split(" or ")      # sub-3-char noise dropped


def test_or_query_dedupes_and_survives_punctuation():
    q = retrieval._or_query("Kaiju, kaiju; KAIJU!")
    assert q == "kaiju"


def test_or_query_empty_for_noise():
    assert retrieval._or_query("a b ?") == ""


# --- retrieval: rendering --------------------------------------------------

def test_render_marks_relayed_provenance():
    """A speaker's claim must not read as Ken's own assertion."""
    out = retrieval.render([
        retrieval.Recall(1, "factual", "Quantum centers are shifting focus",
                         "relayed", 0.5, ["graph"]),
        retrieval.Recall(2, "preference", "Ken prefers neutral tone",
                         "ken_said", 0.4, ["keyword"]),
    ])
    assert "(factual/relayed) Quantum centers" in out
    assert "(preference/Ken) Ken prefers" in out


def test_render_empty_is_empty_string():
    assert retrieval.render([]) == ""
