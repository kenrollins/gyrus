---
id: journal-007-flash-tier-finds-a-home
type: journal
title: "The flash tier finds a home, and PCIe forgives the MoE"
date: 2026-08-11
visibility: public
tags: [infrastructure, l4-fleet, orchestrator, bake-off, models]
related:
  - journal/2026-08-11-first-extraction-dry-run
one_line: "A same-day port of the GB10 model orchestrator to the 4x L4 fleet, gated by measurement: Lightning BF16 TP4 hit 113.8 tok/s at 0.07s TTFT over PCIe — triple the acceptance bar, double its own GB10 number — freeing the GB10's KV budget for the agent's main model."
principle: "When two workloads fight over one accelerator's memory, the cheapest fix may be a second-tier fleet you already own — if you gate the move on measured latency, not vibes."
---

The extraction bake-off left a resource conflict as its residue: the new
flash-lane model and the 120B reasoning model were co-resident on the one
Blackwell box, and the KV cache both needed couldn't be shared. The 120B —
the future main model of the personal agent — was serving inside an 8k
context window with 4.5GB of headroom. Meanwhile four L4s in the rack sat
at literally zero utilization, dismissed as flash-tier hardware because a
dense 31B on them decodes at 15 tok/s (41 with speculative decoding on a
friendly workload — measured by a predecessor project, not guessed).

The insight that unlocked it: the flash candidate is a 3B-active MoE on a
mamba-hybrid backbone. Dense-model intuition says PCIe-coupled L4s are too
slow; MoE arithmetic says per-token reads drop ~10x and the tensor-parallel
allreduce traffic shrinks with them. Nobody had measured it, so the answer
was to build the thing that could.

## The port

The lab already had a model orchestrator on the Blackwell box — load/unload
API, registry, adopt-on-restart, Prometheus — with a comment trail of
hard-won rules (graceful-stop before remove, or the shared compile cache
corrupts; private shm per engine, or torch's op registration dies with a
garbage error; serialize loads off the event loop, or the API freezes for
minutes). Porting it to a discrete-GPU fleet was a same-day job precisely
because those rules were written down where the code lives.

Three changes were architectural, not cosmetic: memory accounting moved
from one unified pool to per-GPU queries; placement became a *GPU set* with
an intersection veto (the discrete-fleet version of "residents' memory
fractions must sum below one"); and a gateway-bridge attach that had lived
as a fragile service hook became part of the load path itself, because a
missed attach breaks gateway routing silently while every local check
passes. One GB10 trick was deliberately left behind: the page-cache
eviction dance exists because unified memory counts file cache against the
GPU; on discrete cards it would only make reloads slower.

## The gate

The move was pre-committed to a measured bar — median 40 tok/s decode and
1.0s first-token on flash-shaped work, or the fleet idea dies. The result
wasn't close: **113.8 tok/s median decode, 0.07s TTFT**, flat across
twenty runs. Double the same model's throughput on the Blackwell box
(where it runs quantized but shares the machine), and 3–7x the dense 31B
on identical silicon. The PCIe penalty everyone braced for was a rounding
error — the MoE's active slice is just too small to hurt.

Two instrument lessons from the gate harness itself, kept for the next
person: the serving engine validates the model id even when only one model
is served (no cosmetic names), and this vLLM build streams thinking as a
`reasoning` delta — a benchmark that only counts `content` tokens will
conclude a thinking model produced nothing at all.

## What it unblocks

The Blackwell box hands its flash duties to the fleet and gives its full
KV budget to the 120B — the 32k serving window the agent integration
actually needs. The fleet stops being idle capital. And the flash lane now
has a control plane symmetric with the big box's, so "load a model on the
L4s" is an API call with a conflict veto instead of a hand-edited systemd
unit. The legacy demo path coexists via container adoption until its
wrapper script is cut over.

## Related

- [The extraction pass met real conversations](2026-08-11-first-extraction-dry-run.md) — where the resource conflict came from
- `xr7620:/data/docker/l4-vllm-orchestrator/` — the code, tests, and gate harness
