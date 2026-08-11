---
id: journal-003-address-answered-twice
type: journal
title: "The address that answered twice"
date: 2026-08-11
visibility: public
tags: [platform, networking, outage, macvlan, docker]
related:
  - adr/0005-embeddings-via-gateway
  - journal/gotchas/dual-homed-container-breaks-dnat
one_line: "A routine key test found every kaiju inference lane dark: two containers on two hosts both claiming 10.0.13.2, and a dual-homed container whose replies escaped un-NAT'd — the gateway had been silently failing over to cloud for its 'local-first' models."
principle: "Silent fallback is an availability feature and an observability bug: the system that keeps working when a backend dies is the system that never tells you the backend died."
---

The first thing the freshly minted service key did was fail. A test
embeddings call through the gateway returned `Cannot connect to host
10.0.13.2:11434` — yet the same Ollama, curled directly from the host,
answered fine with its full model list. Same destination, different result,
depending on who was asking. That is never a model problem; that is a
network telling you a story.

## Narrowing it

From inside the gateway container: connection **refused** — something at
`.2` actively sending RST. From the host: a working Ollama. A chat call to a
different kaiju-routed model failed identically, so this wasn't about
embeddings — every `kaiju/*` lane through the gateway was dark. A GB10-routed
model worked, confirming the key and the gateway itself were fine.

The platform registry said kaiju's Ollama should live at `.230`, guarded by a
kaiju-side firewall accepting only the gateway's address. Testing `.230`
directly from the gateway: **timeout** — not refused, dropped. So the
documented path was broken too, differently. Two bugs, one symptom.

## The capture that explained everything

tcpdump on kaiju's DMZ interface during a gateway connect attempt to `.230`:

```
10.0.13.201 > 10.0.13.230.11434: Flags [S]        ← SYN arrives, firewall accepts
172.25.0.17.11434 > 10.0.13.201: Flags [S.]       ← SYN-ACK leaves... from WHO?
```

The SYN-ACK left kaiju with the **raw docker-bridge address** of the Ollama
container as its source. The gateway had sent a SYN to `.230` and got a
SYN-ACK from `172.25.0.17` — an address it never contacted — so the handshake
could never complete.

`docker inspect` closed the case: the Ollama container is dual-homed. Besides
its bridge network, it holds a macvlan leg *directly on the DMZ VLAN* — at
`10.0.13.2`. That one fact explains both bugs:

- **The `.230` timeout:** inbound SYNs are DNAT'd by the host into the
  container, but the container's *replies* to any DMZ address route out its
  own macvlan leg (connected subnet beats default route), bypassing the
  host's conntrack entirely. The DNAT is never reversed. Asymmetric by
  construction.
- **The `.2` refusal:** the identity provider on the other host had since
  been deployed to its registry-assigned address — also `10.0.13.2`. Two
  containers on two physical hosts, both claiming the same IP. The gateway's
  ARP cache resolved `.2` to the identity provider (which has no port 11434,
  hence RST); the router's ARP cache happened to hold the Ollama container's
  MAC, which is why host-routed traffic still worked. An ARP coin-flip
  deciding which service you reach.

## The part that stings

The gateway's kaiju lanes are configured with fallbacks to free cloud
endpoints. So when every local lane went dark, nothing visibly broke — 
aliased requests silently failed over to the cloud, and the lab's
"local-first" strategy quietly became "cloud-actually" for an unknown number
of days. The failure was only *found* because a brand-new key had no
fallback configured and errored honestly.

Remediation is a platform call, not this project's: drop the legacy macvlan
leg from the Ollama container (the registry design — published port plus
source-restricted firewall — is correct and becomes fully functional the
moment the leg is gone), repoint the gateway's 39 stale `.2` route entries to
`.230`, restart the gateway. Filed to the platform backlog with the evidence.

## Amendment, same day: there was a third bug under the second

Applied with the operator's go-ahead a few hours later — and the two-bug
story turned out to be a three-bug story. With the leg removed and the
routes repointed, the error *changed* rather than vanished: "cannot connect"
became Ollama answering **404**. Every one of the gateway's 39 ollama route
entries appended `/v1` to the backend address, and LiteLLM's native ollama
providers build paths like `{base}/api/chat` — so the gateway had been
requesting `/v1/api/chat`, which Ollama has never served. Endpoint probes
confirmed it (`/v1/api/chat` 404; `/api/chat`, `/v1/chat/completions`,
`/api/embed` all 200). Stripping the suffix from all 39 entries turned every
lane green: embeddings at 1024 dimensions with metered usage, kaiju chat
answering, GB10 unaffected.

The uncomfortable implication: the `/v1` suffix predates today's
address conflict (it's in the oldest surviving config backup), meaning the
kaiju lanes may have been quietly broken — and silently covered by cloud
fallbacks — for longer than either bug we set out to fix. The firewall's own
packet counters agree: the documented gateway-only accept rule had passed
~30 packets since July 28, all of them today's diagnostics. Three bugs, each
masking the next, none visible from the outside because fallback kept every
consumer working. The monitoring lesson writes itself: **alert on fallback
*activation*, not just on failure** — a fallback that fires is a fallback
hiding an outage.

## Related

- [gotcha: dual-homed container breaks DNAT](gotchas/dual-homed-container-breaks-dnat.md)
- [ADR-0005](../adr/0005-embeddings-via-gateway.md) — the decision this outage cannot dent (the path is right; the path was just broken)
