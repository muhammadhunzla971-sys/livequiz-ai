from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    app_name: str = "LiveQuiz AI"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://livequiz:livequiz@postgres:5432/livequiz"
    redis_url: str = "redis://redis:6379/0"
    redis_max_connections: int = 40
    redis_pool_wait_sec: float = 10.0

    jwt_secret: str = Field(default="change-me-in-production", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    player_token_hours: int = 6

    # How many reverse proxies sit in front of the API (Render/Railway = 1, local = 0).
    trusted_proxy_hops: int = 0
    max_body_bytes: int = 1_000_000
    # If set, GET /metrics requires "Authorization: Bearer <token>" (set it in production).
    metrics_token: str = ""

    cors_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"

    # LLM (any OpenAI-compatible endpoint, e.g. Groq)
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_primary_model: str = "openai/gpt-oss-120b"
    llm_fallback_model: str = "openai/gpt-oss-20b"
    llm_timeout_sec: float = 30.0
    llm_max_retries: int = 3
    generation_rate_per_hour: int = 20
    generation_cache_ttl_sec: int = 60 * 60 * 24

    # Realtime
    # Per-IP join attempts per minute. A whole classroom can share one school IP, so keep it
    # roomy; the load test raises it because every simulated player comes from one machine.
    join_rate_per_min: int = 120
    max_players_per_room: int = 300
    answer_grace_ms: int = 500
    ws_max_msgs_per_sec: int = 10
    ws_max_payload_bytes: int = 4096
    room_ttl_sec: int = 60 * 60 * 6
    session_retention_days: int = 90

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, url: str) -> str:
        """Managed hosts hand out postgres:// or postgresql:// URLs (some with ?sslmode=require).

        Our async driver needs the +asyncpg scheme and spells the SSL option `ssl`.
        """
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+asyncpg://" + url[len(prefix) :]
        return url.replace("sslmode=", "ssl=")

    def production_problems(self) -> list[str]:
        """Settings that must never ship to production; checked at startup when ENV=prod."""
        problems = []
        if self.jwt_secret.startswith("change-me") or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be a random string of at least 32 characters")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS must list your real frontend URL, not *")
        if self.frontend_url.startswith("http://localhost"):
            problems.append("FRONTEND_URL still points at localhost")
        return problems

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
