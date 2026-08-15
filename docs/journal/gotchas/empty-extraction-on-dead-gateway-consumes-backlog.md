---
id: gotcha-004-empty-extraction-on-dead-gateway-consumes-backlog
type: gotcha
title: "Returning [] when inference is unreachable lets a batch job erase its own backlog"
date: 2026-08-15
visibility: public
tags: [extraction, gateway, batch, idempotency, failure-modes]
related:
  - journal/2026-08-15-the-backlog-that-could-not-drain
  - adr/0001-port-dont-rebuild
one_line: "An extraction client that swallowed all failures into an empty result made 'the model found nothing worth keeping' indistinguishable from 'no model answered' — so a batch route stamped its work items complete, on time, having learned nothing."
principle: "A tolerant failure path is correct only where the caller cannot act on the difference; the moment a caller commits state on the result, absence-of-answer must be a distinct, loud outcome from answer-is-empty."
---

**Symptom.** A backfill drains a queue of unextracted turns suspiciously fast —
2 windows in 11 seconds against a 70B model that normally takes ~60s per
window — and reports `0 facts, 0 new` for every window. The work items are
marked complete. The backlog counter falls. No error is raised anywhere, the
HTTP route returns `200 OK`, and no error column is populated. Re-running finds
nothing left to do, because there is nothing left: the turns are stamped.

**Mechanism.** The gateway client swallowed every failure into `[]`:

```python
except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as e:
    logger.warning("extract(%s) attempt %d failed: %s", mdl, attempt + 1, e)
    await asyncio.sleep(1.5 * (attempt + 1))
return []
```

That is a *deliberate and correct* design for tolerant parsing — lab models wrap
JSON in fences, prose, and thinking blocks, and a pass that threw on formatting
noise would drop real facts. The bug is that it collapses two different events
into the same value:

- the model answered, and there was genuinely nothing durable in the window
- **no model answered at all**

Downstream, the batch route persists the (empty) fact list and stamps
`extracted_at` in the same transaction — the property that makes it idempotent
and safe to run twice. That property inverts under the collapse: with the
gateway unreachable, "extracted nothing" is written as durably as "extracted
everything," and the turn is never revisited. The tolerant path was written for
a *per-turn* caller that retries; it was inherited by a *batch* caller that
commits.

The trigger needs no exotic conditions. Here it was a routine container restart
of the LiteLLM gateway that happened to overlap the run — 8 connection failures
across ~11 seconds, all three candidate models (primary, union, and fallback)
failing to connect at the transport layer.

**Fix.** Track whether any candidate lane produced an HTTP response at all, and
make the two outcomes structurally different:

```python
responded = False
...
    responded = True          # the lane is alive, whatever it said
...
if not responded:
    raise GatewayError(f"no model answered (tried {', '.join(models)})")
return []
```

Then let each caller choose, because they genuinely differ:

- the per-turn worker catches it and leaves `extracted_at` NULL — the sweeper
  retries it later, which is what the tolerant path always intended
- the batch route returns **503** with the turns untouched, so the client
  retries instead of losing them
- a *secondary* "second opinion" pass is a bonus, so its lane being down is
  logged and tolerated (`asyncio.gather(..., return_exceptions=True)`, raising
  only if the primary failed)

**Boundary of what was tested.** The raise path was verified directly by
pointing `litellm_base_url` at a closed port and confirming `extract_union`
raises `GatewayError` rather than returning facts; the success path was verified
by a real 2-window run producing 39 facts. The original silent-stamp behaviour
was observed live (6 turns stamped with 0 facts, then restored) before the fix.

**The general shape.** "Fail soft, return empty" is a good default for a
*reader* and a dangerous one for a *writer*. Ask which side of that line the
caller is on. If any caller commits state on the strength of the result, an
empty result must not be reachable from an infrastructure failure — otherwise
the quietest possible outage produces the most confident possible record.
