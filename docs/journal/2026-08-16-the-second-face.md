---
id: journal-027-the-second-face
type: journal
title: "The second face"
date: 2026-08-16
visibility: public
tags: [m7, mcp, auth, f3, adr-0003]
related:
  - adr/0003-provider-plus-mcp-face
one_line: "M7 shipped in one pass: bearer auth closed the year's oldest open finding (F3) with a zero-gap cutover that never dropped a Pip capture, and the MCP face now serves the store to any agent — with cross-agent searches feeding the same demand signal Pip feeds."
principle: "A second consumer is the test of a neutral core: if the MCP face needed anything but thin adapters over the same domain calls, the store had a hidden bias toward its first face."
---

ADR-0003 promised one store with two faces and shipped only the first;
F3 sat in the Fable review since 2026-08-13 saying the store was readable
by anyone on the DMZ — flagged, accepted for M0's scratch data, and
increasingly wrong as the store grew 10,000 extracted personal facts.
Working through TASKS.md in order, both closed today.

## Auth without a dropped turn

The constraint wasn't the middleware (a bearer check with constant-time
compare, /health left open for monitoring) — it was the cutover. Pip's
provider is fire-and-forget by design: a 401 on capture would vanish into a
debug log, the exact zero-shaped failure this project keeps hunting. So the
order mattered: the VM's provider and env got the token FIRST (the
pre-enforcement service ignores the extra header), hermes restarted, and
only then did the rebuilt service start enforcing. Measured after: 401
bare, 200 with token, zero 401s from the provider. F3 closed with no
capture window.

## The face itself was an afternoon, which was the point

The openbrain adapter spec (fetched from kaiju, where the retired system
still keeps its docs) mapped almost one-to-one: search_memory /
recent_memory / open_loops / insights / add_memory, read and write cleanly
split, request_id on every call, server-side caps on every limit. Every
tool is a thin call into the same retrieval/persist code Pip uses — the
write tool goes through extraction.persist, so an MCP client's memory is
embedded, near-dup checked, and refused when the embedder is down, exactly
like everyone else's. No side door.

Two gyrus-isms worth recording: MCP searches log retrievals under
`mcp:<request_id>` sessions, and insights browses bump `browse_count` —
so a Claude session searching Ken's memory generates the same
demand-for-retention signal (ADR-0008) and the same recall data the curve
feeds on. The second face isn't a read-only mirror; it is a second organic
usage source for the thesis.

Friction, for the record: the SDK renamed FastMCP to MCPServer and moved
the transport flags; and its DNS-rebinding protection rejects any Host it
doesn't allow-list — right for a browser-adjacent localhost server, wrong
for a server-to-server face addressed by DMZ IP behind a bearer. It is off,
with the reasoning in a comment at the switch.

The store now answers three consumers: the provider (always-on, Pip's
every turn), the MCP face (on-demand, any agent with the token), and the
insights surface (Ken's own browsing). All three feed the same signals.
One store, no drift — the ADR's claim, now load-bearing.
