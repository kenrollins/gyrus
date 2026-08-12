---
id: journal-008-m1-the-memory-remembers
type: journal
title: "Five ways a memory system silently forgets"
date: 2026-08-12
visibility: public
tags: [m1, extraction, retrieval, bugs]
related:
  - adr/0002-tier-by-signal-source
  - adr/0005-embeddings-via-gateway
one_line: "M1 shipped — extraction, hybrid retrieval, and a backfill of five months of real conversation — and every bug found at scale was a silent one: memories that were never stored, never matched, or never surfaced, with no error anywhere."
principle: "In a memory system, the dangerous failures are silent by construction: nothing errors when a fact is never extracted, never matched, or ranked sixth. Build the instrument that shows you WHY a result appeared before you trust the results."
---

M1 was supposed to be the milestone with no surprises. The specification was
unusually complete: two ADRs, a graded golden set, a champion prompt, a
measured model choice. Write the schema, write the extractor, write the
ranker, point it at five months of real conversation.

The code went in fast. Then the corpus arrived — 2,787 messages across 47
sessions of actual work — and produced five bugs in an afternoon. Every one
of them was silent. Not a stack trace among them.

## 1. One bad character ate a whole conference

The extractor asks a model for JSON and parses the array. The 70B emitted a
malformed member somewhere around character 919 — an unescaped quote, most
likely — and `json.loads` refused the entire array. The window returned zero
facts. No error surfaced anywhere: the extractor's contract is "return what
you found", and it found nothing, which is a perfectly ordinary outcome for
a window of pleasantries.

An entire conference session's memories, discarded by one quote mark, and
the only reason anyone noticed was that a side-by-side comparison had
*already* shown what that window should produce. The fix is the shape the
predecessor system had used for the same reason: walk balanced braces and
parse each object independently, so a bad member costs one fact instead of
all of them.

## 2. The keyword leg answered every question with silence

Full-text search in Postgres has a helper that turns a user's phrase into a
query. It ANDs the terms. Ask "how do I like my end of day summaries
formatted" and it demands a memory containing *like* and *end* and *day* and
*summaries* and *formatted* — and there is no such memory, because real
memories are written like "Day summary emails should follow the same
sections and format as the previous day's."

So the keyword leg — the leg that exists precisely because it nails literal
strings — returned nothing on exactly the conversational phrasing an agent
sends. It didn't fail; it matched zero rows, which looks identical to "no
relevant memories". The other two legs filled the slots with noise, and the
result looked like a mediocre ranker rather than a broken one.

## 3. "chat" matched "SalesChat"

The entity leg checks whether a memory's tagged entity appears in the query.
Substring containment, no word boundaries. The entity `chat` — harvested
from "chat for action" — matched the query "SalesChat weekly questions", and
five slots of a five-slot recall went to memories about an unrelated
workflow. Confidently, at a good score, with no way to tell from the output
that anything had gone wrong.

## 4. Every memory knew who Ken was

The entity table's top entries: `ken` on 93 memories, `hermes` on 93, `pip`
on 50. In a *personal* agent's store, the user's own name is on everything,
which means matching it carries no information at all — it is the word "the"
wearing a proper noun's clothes. Classic information retrieval has the
answer (weight each entity by inverse document frequency), and the moment it
went in, rare entities like `NQISRC` started deciding results instead of
being outvoted by a name that means nothing.

## 5. Vector search always returns something

The semantic leg asks for the forty nearest memories. Nearest is not near:
in a small store the fortieth neighbour can be unrelated by any human
standard, and it still arrives ranked, scored, and looking like a result.
Those were the filler rows in every weak query — plausible-looking memories
about cron jobs answering a question about email formatting.

Nearest-neighbour search answers "closest", never "close enough". A cosine
floor is what converts it into a relevance test, and it is the difference
between a recall list of five useful memories and a recall list of two
useful memories padded with three confident irrelevancies.

## What made them findable

One design choice, made for a different reason, turned out to be the
diagnostic that cracked all five: **every recall reports which legs found
it.** That column was added so the hybrid could be audited — proof that no
single leg was doing all the work, per the project's own non-negotiable.

It became the debugger. Results tagged `semantic` alone were noise; results
tagged `graph+keyword+semantic` were always right. Reading a bad result and
seeing *keyword didn't fire at all* pointed straight at the AND-semantics
bug; seeing the graph leg fire on a query with no matching entity pointed
straight at the substring bug. Without that field, the symptom would have
been "recall feels mediocre" — a judgement, not a bug report.

The agreement pattern was strong enough to become a feature: memories found
by multiple independent legs now score higher for exactly the reason the
hybrid is non-negotiable. One leg can be confidently wrong. Three rarely
agree on a wrong answer.

## Where it landed

Extraction runs as a union of two models chosen because they *disagree*
usefully — one returns the domain insights, the other the reference layer of
addresses, versions and open loops. Both idle on the same box, so the second
opinion is free. Recall now returns five relevant memories where it returned
two; the top hit for "what is my Obsidian setup" is the literal vault path,
found by all three legs at once.

One more silent failure worth recording, because it was self-inflicted: the
embedder shares hardware with the extraction models, and under backfill load
it timed out — memories landing with no vector, losing their semantic leg
forever. The fix wasn't to make embedding more reliable but to stop treating
it as a write-time requirement. A vector is now a repairable property: a
sweeper embeds whatever arrived without one. Twenty minutes later the store
had zero unembedded memories and no one had to notice.

## Amendment: the sixth silent failure was mine

Activating the provider on the live agent produced a sixth, and it was the
most instructive — because the code was a faithful implementation of the
documented contract and still wrong.

The provider hook says recall "should be fast — use background threads for
the actual recall and return cached results here", with a sibling hook to
queue that background work after each turn. Implemented literally, that
means the first turn of any session has an empty cache, and every later turn
serves recall for the PREVIOUS question. The agent answered the test question
perfectly from its own built-in memory while the new store logged zero
retrievals: a passing demo, a completely inert memory system, and no error
anywhere.

Measurement settled it: a full hybrid recall from the agent host is ~120 ms.
The contract's caution is written for a cloud memory API, not a service one
hop away on the LAN. Recall is now fetched inline against a hard 2.5 s
deadline — fast path when it's fast, and the turn proceeds memory-less rather
than late when it isn't.

Then the deadline caught something real. Under a concurrent backfill the
query-embedding call stretched past 40 seconds, so recall returned nothing —
while the keyword and graph legs sat idle at 80 ms, perfectly able to answer.
The project's rule is "never vector-only"; the missing half is **never
vector-dependent**. A leg that exists to add relevance must never be able to
veto it. The semantic leg now runs against its own 1.2 s budget and recall
ships with two legs when the third is late.

The live loop closed after that: a real session retrieved five memories,
answered from them, and was captured back into the episodic store.

## Related

- [The handoff survives contact with the source](2026-08-11-the-handoff-survives-contact.md) — why the ranker was greenfield
- [The extraction pass met real conversations](2026-08-11-first-extraction-dry-run.md) — the golden set these bugs were measured against
