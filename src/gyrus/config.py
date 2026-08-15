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
    embed_model: str = "kaiju/mxbai-embed-large"      # ADR-0005; vector(1024)
    # Extraction workhorse. Won the golden-set matrix outright; scale is not
    # the lever (the 120B lost domain facts this model caught).
    extract_model: str = "kaiju/nemotron:70b"
    # Used when the primary lane is down — GB10/L4 lanes are batch-claimed,
    # kaiju's are on-demand, so the fallback deliberately sits on other silicon.
    extract_fallback_model: str = "vllm/nemotron-120b"
    # Second opinion merged into the primary result. Measured 2026-08-12 on the
    # panel window: the 70B returns the DOMAIN insights (ecosystem shift,
    # quantum+HPC coupling, modularity) while gpt-oss returns the REFERENCE
    # layer (three contact addresses, exact format specs, an open loop) — the
    # precise gap the golden-set grading flagged. Complementary, not redundant;
    # both idle on kaiju, so the second pass is free. Empty disables.
    extract_union_model: str = "kaiju/gpt-oss:120b"

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

    # --- retrieval ---
    recall_k: int = 5                  # memories injected per turn
    recall_pool: int = 40              # candidates per leg before fusion
    semantic_floor: float = 0.45       # min cosine; below this is not "related"
    recall_embed_timeout: float = 1.2  # semantic leg's own deadline; miss it, ship 2 legs

    model_config = {"env_prefix": "GYRUS_", "env_file": None}


settings = Settings()
