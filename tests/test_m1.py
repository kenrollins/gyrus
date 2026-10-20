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


# --- ADR-0013: reflective tier projection -----------------------------------

def test_graph_row_shaping_preserves_null_event_time():
    """An absent event_at must stay absent in the graph — 0 would mean
    'happened at the epoch' and poison every temporal traversal."""
    import sys
    import types
    from datetime import datetime, timezone

    sys.modules.setdefault("asyncpg", types.ModuleType("asyncpg"))
    from gyrus import graph

    now = datetime.now(timezone.utc)
    rows = [
        {"id": 1, "tier": "factual", "confidence": 0.7, "event_at": None,
         "created_at": now, "retired_at": None, "superseded_by_id": None},
        {"id": 2, "tier": "knowledge", "confidence": 0.5, "event_at": now,
         "created_at": now, "retired_at": now, "superseded_by_id": 1},
    ]
    out = graph.memory_rows_to_params(rows)
    assert out[0]["event_at"] is None and out[0]["retired_at"] is None
    assert isinstance(out[1]["event_at"], float)
    assert out[1]["superseded_by"] == 1


def test_claude_lane_never_corroborates(monkeypatch):
    """Echo-chamber guard (journal-031): once Claude sessions can READ the
    store over MCP, a session restating a recalled fact in its memory file
    is a repeater, not a witness — the claude lane folds near-dups silently,
    never bumps. Cross-source corroboration must come from non-claude sources."""
    import asyncio

    from gyrus import extraction, gateway

    async def fake_embed(texts, **kw):
        return [[0.1] * 4 for _ in texts]

    monkeypatch.setattr(gateway, "embed", fake_embed)
    monkeypatch.setattr(gateway, "to_pgvector", lambda v: "[0.1]")

    bumps = []

    class Conn:
        async def fetchrow(self, sql, *args):
            if sql.lstrip().startswith("SELECT id, source_key"):
                return {"id": 42, "source_key": "github:kenrollins/gyrus", "sim": 0.99}
            return None
        async def execute(self, sql, *args):
            bumps.append(args)
        async def executemany(self, *a):
            pass

    f = extraction.Fact(tier="knowledge", fact="a fact the store already holds",
                        entities=[], provenance="relayed", source_type="claude")
    written = asyncio.run(extraction.persist(Conn(), [f], turn_id=None,
                                             session_id=None,
                                             source_key="claude:gemma-forge"))
    assert written == 0        # folded, not inserted
    assert bumps == []         # and NO corroboration bump despite different source_key


# --- The second opinion is never answered by the fallback (2026-10-19) -------

def test_candidate_models_fallback_switch(monkeypatch):
    """The union pass asks for a DIFFERENT engine's read; a substitute from
    the fallback lane defeats it (measured: ~110 windows answered by
    lab/reason under the union's name). fallback=False → one candidate."""
    from gyrus import gateway
    from gyrus.config import settings

    monkeypatch.setattr(settings, "extract_model", "lab/extract")
    monkeypatch.setattr(settings, "extract_fallback_model", "lab/reason-strict")
    assert gateway.candidate_models(None) == ["lab/extract", "lab/reason-strict"]
    assert gateway.candidate_models("lab/extract-union") == ["lab/extract-union", "lab/reason-strict"]
    assert gateway.candidate_models("lab/extract-union", fallback=False) == ["lab/extract-union"]
    # Asking for the fallback lane itself must not try it twice.
    assert gateway.candidate_models("lab/reason-strict") == ["lab/reason-strict"]
    # The lane bench blanks the fallback: every lane answers for itself.
    monkeypatch.setattr(settings, "extract_fallback_model", "")
    assert gateway.candidate_models("lab/flash") == ["lab/flash"]


def test_union_pass_skips_instead_of_substituting(monkeypatch):
    """A down union lane → the window is extracted on the primary alone,
    counted as skipped, and the union leg was called with fallback=False."""
    import asyncio

    from gyrus import extraction, gateway
    from gyrus.config import settings

    calls = []

    async def fake_extract(messages, *, model=None, fallback=True, **kw):
        calls.append((model, fallback))
        if model == settings.extract_union_model:
            raise gateway.GatewayError("no model answered (tried lab/extract-union)")
        return [extraction.Fact(tier="factual", fact="Primary fact survives the skip",
                                entities=[], provenance="observed")]

    monkeypatch.setattr(extraction, "extract", fake_extract)
    monkeypatch.setattr(extraction, "UNION_SKIPPED", 0)
    out = asyncio.run(extraction.extract_union([{"role": "user", "content": "hi"}]))
    assert [f.fact for f in out] == ["Primary fact survives the skip"]
    assert (settings.extract_union_model, False) in calls
    assert (None, True) in calls
    assert extraction.UNION_SKIPPED == 1


# --- Content blocks must not crash outcome scoring (2026-10-19) --------------

def test_tool_outcome_reads_list_content_blocks():
    """Pip's zulip vision tool returns content as typed blocks. One such turn
    at the head of the sweeper's queue raised TypeError and silenced outcome
    scoring from 2026-09-01 to 10-19. Text blocks are read; images are not
    evidence either way."""
    from gyrus import outcomes

    msgs = [
        {"role": "tool", "content": [{"type": "image_url", "image_url": {"url": "data:..."}},
                                     {"type": "text", "text": '{"success": true}'}]},
        {"role": "tool", "content": [{"type": "text", "text": "Traceback (most recent call last)"}]},
        {"role": "tool", "content": [{"type": "image_url", "image_url": {"url": "x"}}]},
        {"role": "tool", "content": None},
        {"role": "assistant", "content": [{"type": "text", "text": "I ran it."}],
         "tool_calls": [{"function": {"name": "bash", "arguments": "{\"cmd\": \"ls\"}"}}]},
    ]
    assert outcomes.tool_outcome(msgs) == (3, 1)
    act = outcomes.action_text(msgs)
    assert "I ran it." in act and "bash" in act


def test_render_window_flattens_content_blocks():
    from gyrus import extraction

    out = extraction.render_window([
        {"role": "user", "content": [{"type": "text", "text": "look at this"},
                                     {"type": "image_url", "image_url": {"url": "x"}}]},
        {"role": "assistant", "content": "a chart"},
    ])
    assert "[USER]\nlook at this" in out and "image_url" not in out


# --- review 2026-10-20 / ADR-0014 ---------------------------------------------

def test_tool_outcome_counts_retries_by_tool_name():
    from gyrus.outcomes import tool_outcome_detail
    msgs = [
        {"role": "assistant", "tool_calls": [
            {"id": "a", "function": {"name": "terminal", "arguments": "{\"cmd\":\"ls -la\"}"}}]},
        {"role": "tool", "tool_call_id": "a", "content": "command not found"},
        {"role": "assistant", "tool_calls": [
            {"id": "b", "function": {"name": "terminal", "arguments": "{\"cmd\":\"/bin/ls\"}"}}]},
        {"role": "tool", "tool_call_id": "b", "content": "file1\nfile2"},
        {"role": "assistant", "tool_calls": [
            {"id": "c", "function": {"name": "web_search", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c", "content": "Traceback: boom"},
    ]
    ok, fail, retries = tool_outcome_detail(msgs)
    assert (ok, fail) == (1, 2)
    assert retries == 1          # terminal failed then ran again; web_search did not
    # a failure followed by the same tool only much later is not a retry
    far = msgs[:2] + [{"role": "assistant", "tool_calls": [
        {"id": f"x{i}", "function": {"name": "other", "arguments": "{}"}}]} for i in range(4)] \
        + [{"role": "tool", "tool_call_id": f"x{i}", "content": "ok"} for i in range(4)] + msgs[2:4]
    assert tool_outcome_detail(far)[2] == 0


def test_or_query_strips_leading_dash_so_it_is_not_a_tsquery_not():
    from gyrus.retrieval import _or_query
    q = _or_query("ls -la --help files")
    assert "-la" not in q and "--help" not in q
    assert "help" in q and "files" in q


def test_control_arm_is_deterministic_and_off_at_zero(monkeypatch):
    from gyrus import retrieval
    monkeypatch.setattr(retrieval.settings, "recall_control_every", 8)
    a = retrieval.is_control("sess-1", "what is my bedtime")
    assert a == retrieval.is_control("sess-1", "what is my bedtime ")   # same arm on retry
    hits = sum(retrieval.is_control(f"s{i}", "q") for i in range(800))
    assert 50 < hits < 150                                               # ~1 in 8
    monkeypatch.setattr(retrieval.settings, "recall_control_every", 0)
    assert not any(retrieval.is_control(f"s{i}", "q") for i in range(50))


def test_judge_none_means_no_credit(monkeypatch):
    """Review C4: an unjudged 'followed' at an embedding score below the noise
    floor must not write an outcome. Exercise the decision table directly."""
    from gyrus import outcomes
    decisions = []
    for verdict in (True, False, None):
        followed = True
        confidence = outcomes.OUTCOME_CONFIDENCE
        if verdict is True:
            confidence = outcomes.OUTCOME_CONFIDENCE_LLM
        else:
            followed = False
        decisions.append((followed, confidence))
    assert decisions == [(True, outcomes.OUTCOME_CONFIDENCE_LLM),
                         (False, outcomes.OUTCOME_CONFIDENCE),
                         (False, outcomes.OUTCOME_CONFIDENCE)]


def test_transient_location_state_gets_a_one_day_clock():
    from gyrus.extraction import _clean
    facts = _clean([
        {"tier": "factual", "fact": "Ken's home is approximately 2 miles from the coordinates 35.8954726,-84.14002318", "provenance": "observed"},
        {"tier": "factual", "fact": "Ken's phone is back home", "provenance": "observed"},
        {"tier": "factual", "fact": "Ken is away in Norman, OK, 1221 km from home", "provenance": "observed"},
        {"tier": "factual", "fact": "Ken's usual bedtime is 10:30", "provenance": "observed"},
        {"tier": "knowledge", "fact": "The sensor reports latitude and longitude once a minute", "provenance": "relayed"},
    ])
    by = {f.fact[:12]: f.expires for f in facts}
    assert by["Ken's home i"] == "day" and by["Ken's phone "] == "day" and by["Ken is away "] == "day"
    assert by["Ken's usual "] is None          # durable stays durable
    assert by["The sensor r"] is None          # knowledge is never gated


def test_fenced_empty_array_is_an_answer_not_a_failure():
    import re
    # the exact check chat_json applies (review C5)
    for text in ("[]", "```json\n[]\n```", "<think>nothing here</think>\n[ ]"):
        assert re.search(r"\[\s*\]", text)
    assert not re.search(r"\[\s*\]", "I found nothing worth keeping.")


def test_reconciler_pair_budget_is_split_by_family():
    from gyrus import reconcile
    assert "procedural" in reconcile.RECONCILE_TIERS
    assert set(reconcile.PERSONAL_TIERS) == {"factual", "preference", "procedural", "open_loop"}
    assert reconcile.TIER_RANK["procedural"] > reconcile.TIER_RANK["factual"] > reconcile.TIER_RANK["open_loop"]
