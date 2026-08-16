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


# --- persist: embed backpressure (audit brief #9, journal-021) -------------

def test_persist_refuses_to_insert_undeduped_when_embedder_is_down(monkeypatch):
    """No vector -> no near-dup check -> a duplicate that looks deduped forever
    once the sweeper backfills the embedding. Ken's ruling (2026-08-15): the
    write path fails LOUDLY and the caller retries; it must never insert
    unchecked. (The retrieval path's None-tolerance is separate and intact.)"""
    import asyncio

    import pytest

    from gyrus import gateway

    async def dead_embed(texts, **kw):
        return [None] * len(texts)

    monkeypatch.setattr(gateway, "embed", dead_embed)

    class UntouchableConn:
        def __getattr__(self, name):
            raise AssertionError(f"persist touched the DB ({name}) with no vectors")

    fact = extraction.Fact(tier="factual", fact="the embedder was down for this one",
                           entities=[], provenance="observed")
    with pytest.raises(gateway.GatewayError):
        asyncio.run(extraction.persist(UntouchableConn(), [fact],
                                       turn_id=None, session_id=None))


# --- ADR-0011: event time and expiry ---------------------------------------

def test_clean_accepts_known_expires_and_drops_garbage():
    """The model may only claim day/week/month; anything else means durable.
    Guessing an expiry the words don't state would silently kill real facts."""
    raw = [
        {"tier": "open_loop", "fact": "Ken owes a reply to the NERSC thread this week",
         "provenance": "observed", "expires": "week"},
        {"tier": "factual", "fact": "Ken's vault path is ~/Documents/Obsidian",
         "provenance": "ken_said", "expires": "eventually"},
        {"tier": "preference", "fact": "Ken prefers one-paragraph explainers",
         "provenance": "ken_said"},
    ]
    out = extraction._clean(raw)
    assert [f.expires for f in out] == ["week", None, None]


def test_knowledge_utility_decays_on_event_time_not_ingest_time():
    """A March story ingested in August must decay as March news (ADR-0011).
    created_at measures the ingest job; event_at measures the world."""
    import sys
    import types
    from datetime import datetime, timedelta, timezone

    # consolidate -> db -> asyncpg, which this pure-logic suite doesn't have;
    # the utility function under test never touches a connection.
    sys.modules.setdefault("asyncpg", types.ModuleType("asyncpg"))
    from gyrus import consolidate

    now = datetime.now(timezone.utc)
    base = {"recall_count": 0, "browse_count": 0}
    fresh_ingest_old_news = {**base, "created_at": now, "event_at": now - timedelta(days=150)}
    fresh_ingest_fresh_news = {**base, "created_at": now, "event_at": now}
    no_event_at = {**base, "created_at": now, "event_at": None}

    assert consolidate._knowledge_utility(fresh_ingest_old_news) \
        < consolidate._knowledge_utility(fresh_ingest_fresh_news)
    # NULL event_at keeps today's behaviour exactly
    assert consolidate._knowledge_utility(no_event_at) \
        == consolidate._knowledge_utility(fresh_ingest_fresh_news)


def test_expiry_inferred_from_fact_words_on_ephemeral_tiers_only():
    """v1.3 bench: the model ignored the expires field even with a verbatim
    example, so _clean infers it from the fact's own words — but only on
    open_loop/preference, where frozen ephemera do damage. A knowledge claim
    saying 'this week' stays durable (too often rhetorical)."""
    raw = [
        {"tier": "open_loop", "fact": "Verify the SalesChat delivery process by Monday",
         "provenance": "assistant_suggested"},
        {"tier": "preference", "fact": "Ken wants to avoid processing email tonight",
         "provenance": "ken_said"},
        {"tier": "knowledge", "fact": "Vendors are shipping PQC updates this week",
         "provenance": "relayed"},
        {"tier": "preference", "fact": "Ken prefers one-paragraph explainers",
         "provenance": "ken_said"},
    ]
    out = extraction._clean(raw)
    assert [f.expires for f in out] == ["week", "day", None, None]


# --- M3: LLM tip_followed judge ---------------------------------------------

def test_follow_judge_parses_verdicts_and_tolerates_garbage(monkeypatch):
    """The LLM leg confirms or refutes the embedding leg; anything unparseable
    means None — the embedding verdict then stands. The judge is an upgrade,
    never a dependency (a down judge must not stall outcome scoring)."""
    import asyncio

    from gyrus import gateway, outcomes

    async def fake_chat(system, user, **kw):
        return fake_chat.reply

    monkeypatch.setattr(gateway, "chat_json", fake_chat)

    fake_chat.reply = [{"followed": "yes"}]
    assert asyncio.run(outcomes.judge_followed("tip", "action")) is True
    fake_chat.reply = [{"followed": "no"}]
    assert asyncio.run(outcomes.judge_followed("tip", "action")) is False
    fake_chat.reply = [{"verdict": "banana"}]
    assert asyncio.run(outcomes.judge_followed("tip", "action")) is None

    async def dead_chat(system, user, **kw):
        raise gateway.GatewayError("gateway down")

    monkeypatch.setattr(gateway, "chat_json", dead_chat)
    assert asyncio.run(outcomes.judge_followed("tip", "action")) is None


# --- M6: reconciler routing and survivor rules ------------------------------

def test_reconcile_routes_token_conflicts_to_the_judge():
    """journal-025's band tool called a conflicting substitution 'distinct';
    the reconciler must NOT — same slot with a different value is either a
    distinct fact or a live contradiction, and only reading decides.
    One-sided enumerations stay deterministically distinct (fold loses the list)."""
    import sys
    import types

    sys.modules.setdefault("asyncpg", types.ModuleType("asyncpg"))
    from gyrus import reconcile

    assert reconcile.route("backup_keep set to 3", "backup_keep set to 5") == "judge"
    assert reconcile.route(
        "The command has settings: notePath, templatePath, onFileExists, textVar",
        "To customize the command, add a key binding") == "distinct"
    assert reconcile.route("the watchdog is paused", "the watchdog is running") == "judge"


def test_contradiction_survivor_is_newer_event():
    """The world changed and the newer memory saw it (ADR-0011 event time);
    ties fall to the higher-signal member. Retirement is bi-temporal, so a
    wrong call is recoverable — but the default must still be sane."""
    import sys
    import types
    from datetime import datetime, timedelta, timezone

    sys.modules.setdefault("asyncpg", types.ModuleType("asyncpg"))
    from gyrus import reconcile

    now = datetime.now(timezone.utc)
    old = {"id": 1, "event_at": now - timedelta(days=90), "created_at": now,
           "corroboration_count": 9, "recall_count": 5}
    new = {"id": 2, "event_at": now, "created_at": now,
           "corroboration_count": 1, "recall_count": 0}
    winner, loser = reconcile.pick_survivor(old, new)
    assert winner["id"] == 2                     # newer event beats older signal

    tie_a = {"id": 3, "event_at": None, "created_at": now,
             "corroboration_count": 4, "recall_count": 1}
    tie_b = {"id": 4, "event_at": None, "created_at": now,
             "corroboration_count": 1, "recall_count": 0}
    winner, _ = reconcile.pick_survivor(tie_b, tie_a)
    assert winner["id"] == 3                     # tie -> higher signal
