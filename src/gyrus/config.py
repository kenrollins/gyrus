"""Runtime settings, env-driven.

Secrets live in /data/docker/gyrus/.env (600, never in git) and reach the
process via the compose env_file — nothing here reads files.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supavisor pooler DSN (gyrus.<tenant>@10.0.13.220:5432/gyrus)
    pg_dsn: str
    # Gateway (LiteLLM). Unused in M0; extraction/embeddings arrive in M1.
    litellm_base_url: str = "http://10.0.13.201:4000/v1"
    litellm_api_key: str = ""
    embed_model: str = "kaiju/mxbai-embed-large"  # ADR-0005; vector(1024)

    host: str = "0.0.0.0"
    port: int = 8000
    # Max stored turns returned by the M0 trivial recall.
    prefetch_recent_limit: int = 3

    model_config = {"env_prefix": "GYRUS_", "env_file": None}


settings = Settings()
