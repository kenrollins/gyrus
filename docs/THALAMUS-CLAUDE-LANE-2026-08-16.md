# Proposal: the "claude" lane — consumer-side design for the thalamus audit/build session

**From the gyrus session, at Ken's direction (2026-08-16):** Claude instances
across the lab leave distilled insights in two file shapes — per-project
session memory (`~/.claude/projects/<slug>/memory/*.md`, frontmatter +
markdown, one fact-cluster per file) and repo `CLAUDE.md` contracts. Ken
wants them probed as a knowledge source. Measured on shadesmar alone:
13 project memory dirs, ~100 files, ~268KB, plus 11 CLAUDE.md files —
pre-distilled, attributed, dated by mtime. xr7620 and other hosts have more.

## Why this source is unusually good

These files are already what extraction tries to produce: atomic-ish,
self-contained insights with provenance ("Ken approved X on date", "Y breaks
because Z"). Signal density far above raw docs. They also carry the lab's
cross-project lessons (verification methods, hardware gotchas, decisions)
that no single repo's docs contain.

## Proposed shape (your side; the ADR-0009 pattern, third use)

- **Edge pusher per host** (shadesmar, xr7620, …): walk configured roots —
  `~/.claude/projects/*/memory/*.md` and `/data/code/*/CLAUDE.md` — and POST
  items to `/v1/ingest` with the push token. No thalamus reach-in to home
  dirs; hosts push, like email does.
- **Item mapping:** `source_type="claude"`,
  `source_ref="<host>:<project>:<relative-file>"`, `title` = frontmatter
  name/description or filename, `body` = file content,
  `published_at` = file **mtime** (honest event time; these files are edited
  in place, and your identity+content-digest hash means an edited file
  re-crosses as a new item with a fresh date — exactly right here, these
  files churn).
- **Author:** "claude/<project>" — downstream provenance must NOT read as
  ken_said; gyrus's extraction prompt handles attribution, but the item
  author should make the agent-authorship explicit.

## Consumer side (already done in gyrus, commit pending)

- `claude` added to TRUSTED_SOURCES (agent-authored for Ken's projects =
  the github trust class; no front gate).
- `source_key = claude:<project>` — independence at the project: one
  project's memory restating itself never corroborates; two projects'
  Claudes recording the same lesson does. That cross-project corroboration
  is the most interesting signal this lane can produce.

## Cautions from the gyrus side

1. **Self-reference:** gyrus's own session memory describes gyrus's store
   states and will be ingested into that store. We already ingest the gyrus
   repo's docs, so this is consistent — but flag it; if it ever gets weird,
   exclude the gyrus project's dir at the pusher.
2. **Overlap with the github lane:** repo CLAUDE.md files are usually in
   github and already ingested. Either exclude CLAUDE.md from the github
   adapter or from this pusher — one owner per file, or the same fact
   arrives from two source_keys and self-corroborates legitimately-looking.
   Recommend: this lane owns CLAUDE.md (it has the mtime and the local,
   possibly-unpushed version); add `CLAUDE.md` to the github adapter's
   exclusions.
3. **Volume**: small (hundreds of items, KB-scale) — no pacing concerns.

Nothing here is urgent; it's a clean adapter + pusher on your side whenever
the session picks it up. The gyrus side is deployed and waiting.
