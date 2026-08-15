# ADR-0012: Request a shape, never a model — gyrus config names lab/* tiers

- **Status:** Accepted
- **Date:** 2026-08-15
- **Deciders:** Ken

## Context

gyrus's config hardcoded four backend model ids (`kaiju/nemotron:70b`,
`vllm/nemotron-120b`, `kaiju/gpt-oss:120b`, `kaiju/mxbai-embed-large`). Ken:
*"what we were going for was model shape — and we could always swap the actual
models out in the background. If that is still a valid concept, I say we
commit to it."* The lab contract asks the same thing (tiers, not model names),
and ADR-0010 exposed the cost of not having it: `lab/flash` and
`vllm/nemotron-lightning-l4` were one backend under two names, and half the
eval history compared a lane to itself. The original blocker — the gyrus key
lacked scope beyond `lab/flash` — was cleared by Ken on 2026-08-15
("swap those gateway keys to lab/<model type> and add whatever you need").

## Decision

gyrus requests **shapes**; the gateway owns the shape→engine binding:

| config field | shape | engine behind it (2026-08-15, measured in ADR-0010) |
|---|---|---|
| `embed_model` | `lab/embed` | mxbai-embed-large on kaiju — byte-identical to the ADR-0005 binding |
| `extract_model` | `lab/extract` | nemotron:70b on kaiju — holds the JSON contract 6/6 windows |
| `extract_union_model` | `lab/extract-union` | gpt-oss:120b on kaiju — engine-diverse second opinion (2% overlap) |
| `extract_fallback_model` | `lab/reason` | nemotron-120b on the GB10 — non-kaiju silicon, outage-independent |

`lab/extract` and `lab/extract-union` are new gateway tiers added for this
(the existing tiers had no extraction shape, and binding extraction to the
flash *engine* is exactly what ADR-0010 measured against: dropped JSON
contract on 2/6 windows). `lab/reason` is a true collapse — the fallback's
engine and `lab/reason`'s were already the same GB10 backend under two names.

The key keeps the concrete `kaiju/*`/`vllm/*` ids **alongside** the tiers so
`bench_lanes.py` can still address engines directly — the bench's job is
precisely to look behind the indirection.

## Consequences

- Swapping an engine becomes a gateway-config edit plus a `bench_lanes.py`
  pass. gyrus code and config never change; the `extractor` stamp on new
  memories reads `lab/extract:v1.2`, which stays true across engine swaps.
- The eval-history failure class "two names, one backend" is now structural:
  the gateway is the single place bindings live, commented with the evidence.
- The fallback timeout (`extract_fallback_timeout`, 900s) keys off the
  `lab/reason` name — the shape carries its operational contract with it.
- Engine swaps behind a shape MUST re-run the golden set first (the binding
  comment in the gateway config says so at the point of edit). A shape name
  that quietly changes engines is the ADR-0010 failure with better branding.
