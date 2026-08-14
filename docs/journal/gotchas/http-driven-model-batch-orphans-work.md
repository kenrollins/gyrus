---
id: gotcha-003-http-driven-model-batch-orphans-work
type: gotcha
title: "Driving a long model-bound batch over synchronous HTTP orphans work under load"
date: 2026-08-15
visibility: public
tags: [ingestion, extraction, http, batch, gateway]
related:
  - journal/2026-08-14-the-loudest-week-is-not-the-truest
one_line: "A one-request-per-batch ingest loop looked like it was failing (every curl returned empty) while the server quietly finished each batch anyway — the client timeout was shorter than a batch of model calls, so work committed but the client never saw it, causing wasteful re-extraction and a false failure signal."
---

**Symptom.** An HTTP endpoint that extracts a batch of documents (one LLM call
each) into memory. Called in a loop — one request per batch, `drain=false`,
cursor persisted server-side. Every response comes back empty; the client logs
`BAD/EMPTY (timeout?)` for 40+ consecutive batches. Yet the ingest cursor keeps
advancing and the memory count keeps climbing. It looks broken and working at
the same time.

**Mechanism.** Each batch is N sequential model calls. Under gateway
contention (a second consumer using the deep tier), per-call latency rose from
~8s to ~27s+, so a 30-doc batch outlasted the client's `-m` timeout. When the
client gives up, the server's request handler is **not** cancelled — it runs to
completion, commits the facts per-item, and advances the cursor. The client,
having already timed out, issues the next request from the *new* cursor. Net:
the job progresses, but every response is lost, and any batch the server
happened to cancel mid-flight (facts written, cursor not yet advanced) gets
**re-extracted** on the next call — burning gateway time on dedup-suppressed
duplicates. Shrinking the batch (30→10) didn't help: latency had risen enough
that even 10 calls outlasted the timeout.

**Fix.** Stop driving a long, model-latency-bound job over synchronous HTTP.
Run it **server-side and detached** — inside the container, one process, no
client connection to time out:

```
docker exec -d gyrus sh -c 'python3 /tmp/drain.py > /tmp/drain.log 2>&1'
```

The whole backlog (~640 docs) then drained in one uninterrupted pass; monitor
by polling the cursor and log, not by holding a connection open. The HTTP
endpoint stays fine for *interactive* single-batch calls — the antipattern is
only using it as the driver for a job whose wall-clock is unbounded by design.

**Boundary.** No data was corrupted by the false failures — the cursor advances
monotonically to the max id pulled, and write-time dedup (fact_hash + cosine)
blocks duplicates — so even overlapping concurrent drainers produced no gaps and
no double-writes. The cost was wasted gateway time and a misleading log, not
integrity. Measured 2026-08-15 during the github knowledge backfill (830 docs →
6,344 facts).
