Load the full gyrus corpus and treat this session as a research interview:
the user is likely preparing presentations, writing journal entries, or
stress-testing insights from the build — not asking for code changes.

Read, in this order:
1. `BRIEF.md` and `docs/design/ARCHITECTURE.md`
2. Every ADR in `docs/adr/`
3. `docs/journal/index.md`, then every journal entry and gotcha it lists
4. `docs/references/SOURCES.md`
5. `PLAN.md` + `TASKS.md` for current build state

Then answer questions with these rules:
- Cite `path:section` for every claim so the user can pull the source into
  a deck or doc.
- Distinguish **measured** (a number with provenance in a journal entry),
  **decided** (an ADR), and **planned** (PLAN/TASKS) — never blur them.
- If an ADR is contradicted or refined by a later journal entry, flag the
  tension explicitly rather than papering over it.
- When asked for presentation material, prefer entries with a `principle:`
  frontmatter field — that field is the intended slide-level claim, and the
  entry body is its evidence.
- Respect `visibility: internal` — flag internal-only material as such
  whenever output is destined for the public site or a customer audience.
