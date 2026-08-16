"""Runtime settings, env-driven.

Secrets live in /data/docker/gyrus/.env (600, never in git) and reach the
process via the compose env_file — nothing here reads files.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supavisor pooler DSN (gyrus.<tenant>@10.0.13.220:5432/gyrus)
    pg_dsn: str

    # --- inference (non-negotiable #5: only ever the gateway) ---
    # The platform's `new-tenant` writes LITELLM_* unprefixed into
    # /data/docker/<app>/.env; honour that convention as well as GYRUS_*.
    litellm_base_url: str = Field(
        default="http://10.0.13.201:4000/v1",
        validation_alias=AliasChoices("GYRUS_LITELLM_BASE_URL", "LITELLM_BASE_URL"))
    litellm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GYRUS_LITELLM_API_KEY", "LITELLM_API_KEY"))
    # MODEL-SHAPE INDIRECTION (ADR-0012, Ken 2026-08-15): gyrus names the SHAPE
    # of the work; the gateway maps shapes to engines. Swapping an engine is a
    # gateway-config change plus a bench_lanes.py pass — never a gyrus change.
    # The measured bindings behind these names (as of 2026-08-15, ADR-0010):
    #   lab/embed         -> mxbai-embed-large on kaiju (ADR-0005; vector(1024))
    #   lab/extract       -> nemotron:70b on kaiju (holds the JSON contract 6/6)
    #   lab/extract-union -> gpt-oss:120b on kaiju (engine-diverse 2nd opinion)
    #   lab/reason        -> nemotron-120b on the GB10 (non-kaiju silicon)
    embed_model: str = "lab/embed"
    # Extraction workhorse — see ADR-0010 for why this shape binds to the 70B.
    # (The old "120B lost domain facts" claim is discredited; same ADR.)
    extract_model: str = "lab/extract"
    # Used when the primary lane is down. lab/reason deliberately sits on
    # non-kaiju silicon (the GB10), so a kaiju outage can't take both lanes.
    extract_fallback_model: str = "lab/reason"
    # That silicon is slow on real windows: ADR-0010's addendum measured this
    # lane exceeding the default 300s chat_json ceiling on 4 of 6 golden
    # windows — the safety net failed exactly when it was needed. The lane only
    # answers when kaiju is gone and extraction is offline work, so give it
    # room rather than repointing at a faster lane that drops the JSON
    # contract (ADR-0010).
    extract_fallback_timeout: float = 900.0
    # Second opinion merged into the primary result. Measured 2026-08-12 on the
    # panel window: the primary returns the DOMAIN insights (ecosystem shift,
    # quantum+HPC coupling, modularity) while the union engine returns the
    # REFERENCE layer (three contact addresses, exact format specs, an open
    # loop) — the precise gap the golden-set grading flagged. Complementary,
    # not redundant. Empty disables.
    extract_union_model: str = "lab/extract-union"

    host: str = "0.0.0.0"
    port: int = 8000

    # --- extraction ---
    extract_char_budget: int = 24000   # per window; long sessions are chunked
    extract_concurrency: int = 2       # parallel windows against one 70B lane
    # How long the sweeper leaves backfill turns alone before treating them as
    # stranded. Long enough not to race a running backfill, short enough that a
    # dead one surfaces in days rather than never (worker._sweeper).
    backfill_grace_hours: int = 24
    dedupe_threshold: float = 0.93     # cosine at/above this = corroboration

    # --- auth (M7 / Fable F3) ---
    # Bearer token for the API and MCP face. Empty = open (the pre-M7 LAN
    # posture); set = required on everything except /health. F3's finding:
    # the store outgrew the reachability decision made against M0's episodic
    # scratch — ~10k extracted personal facts deserve a credential even
    # LAN-side, and the MCP face must never ship without one.
    api_token: str = ""

    # --- consolidation (M2) ---
    # The dream sweeper runs a committed consolidation whenever the store's
    # max(consolidated_at) is older than this. 0 disables (manual only).
    # Restart-proof: cadence is read from the store, not process uptime.
    consolidate_interval_hours: int = 24

    # --- outcomes (M3) ---
    # The LLM tip_followed leg (outcomes.py): confirms/refutes the embedding
    # leg's "followed" verdicts. lab/flash is enough — one yes/no about one
    # tip and one action log; contract adherence doesn't matter at that size.
    outcome_llm_judge: bool = True
    outcome_judge_model: str = "lab/flash"

    # --- retrieval ---
    recall_k: int = 5                  # memories injected per turn
    recall_pool: int = 40              # candidates per leg before fusion
    semantic_floor: float = 0.45       # min cosine; below this is not "related"
    recall_embed_timeout: float = 1.2  # semantic leg's own deadline; miss it, ship 2 legs

    model_config = {"env_prefix": "GYRUS_", "env_file": None}


settings = Settings()
