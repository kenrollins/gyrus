# Shadesmar handoff — finish the M0 demo (and open the return channel)

**Audience:** the Claude Code session running as `agent` on shadesmar.
**Fetched via:** `ssh xr7620 cat /data/code/gyrus/docs/SHADESMAR-HANDOFF.md`
**State on the xr7620 side (all done, verified 2026-08-11):** the gyrus
memory service is live at `http://10.0.13.11:8000` (health returns
`{"ok": true}`), the episodic store works end-to-end, and the gateway's
kaiju lanes (including embeddings) are fixed and green. The only missing
M0 piece is on YOUR host: install the provider into Hermes and observe a
real captured turn + injected recall.

Ken's prompt to paste into Claude Code on shadesmar:

> Read the handoff: `ssh xr7620 cat /data/code/gyrus/docs/SHADESMAR-HANDOFF.md`
> — then follow it.

## Step 0 — open the return channel — ✅ DONE 2026-08-11

Keys are set up in both directions: `agent@shadesmar` ⇄ `rollik@xr7620`
(`ssh xr7620` from shadesmar lands as rollik via ~/.ssh/config). The xr7620
session can drive shadesmar directly.

## Step 1 — sanity: can you reach gyrus?

```bash
curl -s -m 5 http://10.0.13.11:8000/health
# expect: {"ok":true,"version":"0.1.0","turns_stored":N}
```

## Step 2 — SYSTEM PREP: upgrade + stabilize (do all of this BEFORE gyrus)

State as recon'd from xr7620 on 2026-08-11 (verify, don't trust — it may
have moved):

- Checkout `~/.hermes/hermes-agent` at `1ef19bad9` (2026-06-27) — ~8,500
  commits behind origin/main. venv Python 3.11.15. 15 GB free on /.
- Working tree clean, BUT a leftover autostash exists:
  `stash@{0}: hermes-update-autostash-20260627-185519`.
- Pip is LIVE: `gateway run` process serving Zulip. Model:
  `gpt-5.4` via `openai-codex`; `providers: {}` is empty — the lab-gateway
  conversion (integration packet Phase 1) has NOT happened yet.
- Built-in memory: `state.db` 232 MB (per-turn capture — this is the future
  gyrus backfill corpus), `kanban.db`, `verification_evidence.db`.
  MEMORY.md/USER.md were not at `~/.hermes/` — locate them during prep.
- Backups dir has a `pre-update-2026-06-27` zip — that's the pattern to
  repeat.

Prep sequence — **one change per restart, never stacked**:

1. **Snapshot first.** `hermes backup` if the CLI offers it, else zip
   HERMES_HOME (state.db included; 232 MB is fine). Record the rollback SHA
   (`1ef19bad9`) and copy `config.yaml` aside. The June autostash suggests
   `hermes update` is the blessed upgrade path — check `hermes update --help`
   before hand-rolling git pull.
2. **Deal with the autostash.** `git stash show -p stash@{0}` — apply it
   consciously or drop it; don't let an upgrade eat it silently.
3. **Upgrade.** ~6 weeks of drift. After pulling, check `requires-python`
   against the venv's 3.11 — if main now wants 3.12+, rebuild the venv.
   Reinstall deps. Expect config-schema drift across 8,500 commits: diff
   `config.yaml` against the new example/reference, run any doctor/migration
   command, and update `MIGRATION_TRACKER.md` (the house habit).
4. **Restart Pip at a quiet moment and verify baseline**: Zulip responds,
   a turn completes, `state.db` still growing, logs clean. Do NOT proceed
   to gyrus until Pip is stable on the new build — otherwise two variables
   are moving and neither can be blamed.

## Step 3 — activate the gyrus provider (second restart)

The plugin is ALREADY STAGED at `~/.hermes/plugins/gyrus/` (copied
2026-08-11, written against current-main's MemoryProvider ABC). Activate:

```yaml
# in ~/.hermes/config.yaml
memory:
  provider: gyrus
```

`GYRUS_BASE_URL` defaults to `http://10.0.13.11:8000` inside the plugin;
set it in Pip's environment only if the address ever changes. Restart,
then confirm the provider loaded (startup logs, or `hermes memory` status).

The provider is one stdlib-only file — no pip installs. It fails soft by
design: if gyrus is unreachable, recall is empty and writes are dropped;
Hermes never blocks on memory.

## Step 4 — the M0 demo of record

1. Start a Hermes session, say something memorable and non-trivial
   (trivial greetings are gated out of prefetch by Hermes core), complete
   the turn.
2. Verify capture: `curl -s http://10.0.13.11:8000/health` — `turns_stored`
   should have incremented. (Or ask the xr7620 session to check the row.)
3. Start a NEW session and ask something related. Before the turn runs,
   the provider's prefetch should inject a `[gyrus] recent context from
   earlier sessions:` block. Confirm it appears in the model's context
   (Hermes debug/verbose, or just observe the model knowing it).
4. Report results back (Step 0 makes this easy: write a note to
   `xr7620:/data/code/gyrus/docs/shadesmar-notes/` — the directory exists).

M0 recall is DELIBERATELY dumb (most recent turns from other sessions).
Relevance ranking is M1. Do not fix it here.

## Known limitations to not trip over

- `prefetch` returns whatever the last `queue_prefetch` cached — on the very
  first turn of a fresh process it may be empty. That's the contract
  (fast cache reads), not a bug.
- Non-primary contexts (cron, subagents, flush) skip writes on purpose.
- The provider keeps a per-process turn counter, reset on `/reset` — turn
  indexes are advisory in M0.

## Step 5 — memory-systems audit (BEFORE wiring gyrus into daily use)

Recon from xr7620 (2026-08-11) found Pip's memory is not one system — it's
at least four, and one "retired" system is still live:

| System | State | Facts |
|---|---|---|
| Hermes built-in | active | `state.db` 232 MB per-turn capture; `memories/MEMORY.md` + `USER.md` |
| **openbrain via MCP** | **STILL LIVE** | `mcp_servers.openbrain → kaiju:7778/mcp`; a bare python process serves it (no container); DB `openbrain` on kaiju's Supabase: **502 memories, 492 embedded, 2026-03-13→08-07, 342 owned by instance `pip`** — written to 4 days ago |
| honcho | remnant | `honcho: {}` in config — confirm inactive, then remove |
| direct kaiju ollama | provider config | `base_url: http://kaiju.home.arpa:11434/v1` — bypasses the lab gateway; fold into Phase 1 |

Also in `mcp_servers:`: `localhost:8417` and `kaiju:8413` — identify both
while auditing (are they memory-adjacent?).

**Shadesmar side of the audit (this session):**
1. From `state.db` / logs, determine which openbrain MCP tools Pip actually
   calls (add_memory? search_memory? open_loops?) and roughly how often —
   that tells us what gyrus must serve on day one vs. what was idle wiring.
2. Confirm honcho is dead config; note anything else memory-shaped.
3. Write findings to `xr7620:/data/code/gyrus/docs/shadesmar-notes/`.

**xr7620/gyrus side (the other session owns this):**
- ~~openbrain importers~~ — CANCELLED after content audit (see
  `docs/references/OPENBRAIN-AUDIT.md`, final verdict): MEMORY.md/USER.md
  already hold the durable facts in better form; openbrain is a time
  capsule. Snapshot kept at `kaiju:~rollik/openbrain-snapshot-2026-08-11.sql`.
- The backfill is instead a **one-time extraction scan over Hermes's own
  signals**: `state.db` (158 sessions / 10,467 messages, May→now) through
  the M1 extraction pass, plus MEMORY.md/USER.md as seed facts.

**Cutover sequence (simplified by the audit):**
1. gyrus provider goes live (Step 3/4) — openbrain MCP can coexist briefly.
2. Ken (or this session) skims
   `xr7620:/data/code/gyrus/docs/shadesmar-notes/openbrain-keepers-review.md`
   (26 rows, 10 minutes); anything MEMORY.md lacks gets added there by hand.
3. **Write-freeze openbrain**: remove its `mcp_servers:` entry from Pip's
   config; stop the orphan python process on kaiju:7778.
4. Archive the DB whenever convenient — the snapshot is the record.

## After M0 — the shadesmar work queue (each its own session/restart)

- **Integration packet Phase 1** (NOT yet done — `providers: {}` is empty):
  point Hermes at the lab gateway (`http://10.0.13.201:4000/v1`, key at
  `xr7620:/data/docker/gateway/pip-hermes.key`), main slot
  `vllm/nemotron-120b`, flash aux slots `vllm/qwen-35b`, keep OpenAI as
  `fallback_providers` (that's the rollback). The kaiju lanes were fixed
  2026-08-11, so `kaiju/*` models work too. See
  `xr7620:/data/code/dmz/docs/HERMES-INTEGRATION.md`. Keep this change
  SEPARATE from the gyrus flip — different restart, different blame radius.
- **Content population into gyrus**: `state.db` (232 MB per-turn capture)
  is the backfill corpus; plus MEMORY.md/USER.md once located, and the
  kanban/verification DBs as candidates. Plan a one-shot export →
  `POST /v1/turns` so the M2 dream pass has history to consolidate on day
  one. Zulip history backfill is separate (gyrus M6).
- Phase 2 of the packet (lab tool discovery via the portal `/api/tools`).
