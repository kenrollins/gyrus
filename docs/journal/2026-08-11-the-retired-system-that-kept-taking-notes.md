---
id: journal-005-retired-system-kept-taking-notes
type: journal
title: "The retired system that kept taking notes"
date: 2026-08-11
visibility: public
tags: [migration, openbrain, audit, mcp]
related:
  - adr/0005-embeddings-via-gateway
  - SHADESMAR-HANDOFF
one_line: "The predecessor memory system, retired months ago on paper, turned out to be live wiring: still MCP-served by a bare python process, still written to four days ago, holding 502 memories — embedded, by luck or lineage, with gyrus's exact model and dimension."
principle: "Retirement is a state of the config, not of the roadmap — audit what the agent actually calls before assuming a system is dead, and sequence write-freeze before export before delete."
---

The design docs are unambiguous: the predecessor memory system is "retired,
mined for patterns." Its address was even reassigned to this project — the
successor inheriting the memory-service address, poetically.

Then a pre-integration audit of the agent's actual config found the
predecessor in the `mcp_servers:` block, resolving to a live port. No
container — the container was indeed retired — just a bare python process
that survived it, still serving the MCP face. The database behind it: 502
memories, 492 with embeddings, a written-to date four days ago, and 342
rows owned by the agent we're building the replacement for. The system was
retired everywhere except where it mattered: the agent kept calling it, and
it kept answering.

Nobody decided this. The retirement removed the *deployment* but not the
*config entry*, and an MCP server that still answers is indistinguishable
from one that's supposed to. The agent had no way to know, and neither did
anyone else, because working wiring is silent — the same lesson as this
morning's gateway fallbacks, wearing different clothes. Two entries, one
day, one moral: **systems don't announce their own obsolescence; you have
to go look.**

Two genuinely good consequences:

1. **The migration corpus is real.** Five months of accumulated memories
   about the user is exactly the cold-start material the new store wants —
   plus entity and open-loop tables that map cleanly onto the M4 schema.
2. **The vectors migrate verbatim.** The predecessor embedded with
   mxbai-embed-large at 1024 dimensions — the model and dimension this
   project independently chose hours earlier (ADR-0005, picked partly
   *because* it was the lineage's one production precedent). No
   re-embedding pass; the columns line up.

The cutover is now written down as a sequence rather than a vibe: new
provider goes live alongside the old MCP (different slots, no conflict);
write-freeze the old system by removing its config entry only once the new
recall is trusted; export → import once the target schema exists; delete
last, never first. A protective pg_dump is already taken.

## Related

- [ADR-0005](../adr/0005-embeddings-via-gateway.md) — the dimension that accidentally matched
- [The address that answered twice](2026-08-11-the-address-that-answered-twice.md) — the same silence, in network form
