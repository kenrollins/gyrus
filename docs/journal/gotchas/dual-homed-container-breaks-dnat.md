---
id: gotcha-001-dual-homed-container-breaks-dnat
type: gotcha
title: "A dual-homed container silently breaks its own published ports"
date: 2026-08-11
visibility: public
tags: [docker, macvlan, networking, dnat]
related:
  - journal/2026-08-11-the-address-that-answered-twice
one_line: "Give a container both a published port and its own macvlan leg on the same subnet as its clients, and DNAT'd connections hang forever: replies exit the macvlan leg and bypass the host's conntrack un-NAT."
---

**Symptom.** Clients on subnet S connect to `host:port` (a Docker published
port). SYN arrives, firewall accepts, and the connection still times out.
Packet capture shows the SYN-ACK leaving with the container's **raw bridge
IP** (e.g. `172.25.0.17`) as source — an address the client never dialed, so
its kernel ignores the reply.

**Mechanism.** The published port works by DNAT on the host: inbound
`hostIP:port → containerBridgeIP:port`, with conntrack reversing the
translation on replies. But if the container *also* has a macvlan leg on
subnet S, the container's routing table has a connected route to S via that
leg — more specific than its default route through the bridge. Replies to
any client on S exit the macvlan leg directly, never traverse the host
network stack, and the DNAT is never reversed. The connection is asymmetric
by construction and can never complete.

**The paired trap.** The macvlan leg's address is easy to forget it exists.
If that address is later reassigned to another service (registry says it's
free; the container still holds it), you get an L2 address conflict where
*which* service answers depends on each client's ARP cache — some clients
reach one, some the other, and both behaviors look stable until an ARP
entry expires.

**Fix.** One network personality per server container: either publish the
port (bridge + DNAT + host firewall) or give it the macvlan leg and talk to
it directly — never both when clients share the macvlan's subnet.
`docker network disconnect <macvlan> <container>` removes the leg live.

**Verified.** 2026-08-11, tcpdump on the serving host's VLAN interface;
lab Ollama host, gateway as client.
