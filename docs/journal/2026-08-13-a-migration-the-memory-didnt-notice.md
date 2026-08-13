---
id: journal-012-migration-the-memory-didnt-notice
type: journal
title: "A migration the memory didn't notice"
date: 2026-08-13
visibility: public
tags: [architecture, migration, boundaries, adr-0004]
related:
  - adr/0004-own-dmz-service
  - adr/0007-thalamus-ingestion-boundary
one_line: "Pip moved host, hypervisor, and network zone — from a Proxmox VM on the LAN to a libvirt VM in the DMZ — and gyrus, its memory, needed zero changes, because the service boundary was drawn so the client could be relocated without the service ever knowing."
principle: "A boundary is well-placed when one side can be completely relocated and the other never learns of it. Test your seams by asking what breaks when the thing on the far side moves."
---

Pip migrated into the DMZ today — a different host, a different hypervisor
(Proxmox → libvirt), a different network zone (LAN → VLAN-13), a new address.
The kind of move that usually means a day of chasing broken assumptions.

gyrus didn't change a line. The memory loop was re-verified minutes after
cutover: a turn on the relocated agent captured to the store and recalled from
it, in-zone now, at the same latency. Not one config edit, not one restart on
the memory side.

That is worth a note, because it was not luck — it was a decision made months
earlier that looked, at the time, like the more expensive option. ADR-0004 put
gyrus in its own service with its own address and made the Hermes side a *thin
client*: the agent calls the memory, the memory never calls the agent. The
alternative — co-locating memory inside the agent process — was simpler to
build and would have made this migration a data-migration too: move the agent,
move the memory, reconcile both, pray.

Instead the migration touched only the client. Everything gyrus knew about Pip
was "someone will call me"; who that someone is, and where they live, was never
gyrus's concern. So Pip could be lifted out of one machine and set down in
another and the memory simply kept answering.

The general shape is worth carrying to the other boundaries this project is
drawing — the thalamus ingestion split (ADR-0007), the future RAGFlow line.
The test for each is the same question this migration just answered by
accident: *what breaks when the thing on the far side moves?* If the answer is
"nothing, it just calls a stable contract," the seam is in the right place. If
moving one side means surgery on the other, the boundary is drawn through the
middle of something that should have been whole.

## Related

- [ADR-0004](../adr/0004-own-dmz-service.md) — the thin-client decision this validated
- [ADR-0007](../adr/0007-thalamus-ingestion-boundary.md) — the next boundary to hold to the same test
