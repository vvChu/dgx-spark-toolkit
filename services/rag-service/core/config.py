from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field, model_validator, SecretStr

# Sentinel values that must never be used as real credentials
_WEAK_PASSWORDS = frozenset({
    "password123", "placeholder_password", "bim_secure_pass_2026",
    "litellm_pwd", "minioadmin", "placeholder_key", "changeme",
})


class Settings(BaseSettings):
    # Milvus Configuration
    MILVUS_HOST: str = "milvus-standalone"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "legal_docs_v11"

    # Neo4j Configuration
    # Accepts both NEO4J_PASSWORD and the legacy NEO4J_PASS env var name
    NEO4J_URI: str = "bolt://neo4j-graph:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("NEO4J_PASSWORD", "NEO4J_PASS"),
    )

    # LiteLLM / LLM Gateway Configuration
    VLLM_API_BASE: str = "http://ai-gateway:4000/v1"
    VLLM_MODEL: str = "rag-core"
    LITELLM_MASTER_KEY: SecretStr = SecretStr("")
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    DEFAULT_RAG_MODEL: str = "rag-light"
    JSON_MODEL: str = "rag-core"

    # Infrastructure / RAG Settings
    GPU_ENABLED: bool = True
    ENABLE_HYDE: bool = False
    MAX_OCR_CONCURRENCY: int = 1
    MAX_WORKERS: int = 2
    MAX_DIGITAL_WORKERS: int = 2

    # Database & Redis
    DATABASE_URL: str = ""
    REDIS_URL: str = "redis://litellm-redis:6379/1"

    # Device Control
    FORCE_CPU_RERANKER: bool = False
    FORCE_CPU_EMBEDDING: bool = False

    # Vision & Fast Realtime Models (ingestion & retrieval pipeline) — Capability Aliases
    PRIMARY_VISION_MODEL: str = "ocr-primary"
    FALLBACK_VISION_MODEL: str = "ocr-fallback"
    REALTIME_CHAT_MODEL: str = "fast-realtime"
    TABLE_VISION_MODEL: str = "ocr-primary"
    TABLE_SUMMARY_MODEL: str = "text-gemma"
    REALTIME_CHAT_TIMEOUT_SECONDS: float = 3.0
    OCR_WORKER_URL: str = "http://ocr-worker:8000"

    # Paths
    PDF_DIR: str = "/app/data/pdf"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173"

    # Semantic cache tuning — exposed here so they can be adjusted via env without rebuilding
    ENABLE_SEMANTIC_CACHE: bool = True
    SEMANTIC_CACHE_THRESHOLD: float = 0.92
    SEMANTIC_CACHE_TTL_SECONDS: int = 3600
    SEMANTIC_CACHE_REDIS_ENABLED: bool = True  # Context Lake: persist cache to Redis

    # Retrieval scoring weights — tune via env to calibrate ranking quality
    RERANK_WEIGHT: float = 0.8
    MILVUS_WEIGHT: float = 0.2
    TABLE_BOOST: float = 0.2
    VALIDITY_BOOST_ACTIVE: float = 0.15
    VALIDITY_PENALTY_OUTDATED: float = -0.3

    # Cross-encoder candidate caps. 60 is temporary until MRR is measured at 30/60/100.
    RERANK_MAX_CANDIDATES: int = 60
    RERANK_EXACT_CANDIDATES: int = 20
    RERANK_AGENTIC_HOP2_MIN_QUOTA: int = 20

    # Context Lake: Session Memory
    SESSION_MEMORY_TTL: int = 7200  # 2 hours

    # Telegram Notifications
    TELEGRAM_BOT_TOKEN: SecretStr = SecretStr("")
    TELEGRAM_CHAT_ID: str = ""

    # Data Export Settings
    EXPORT_PROCESSED_DATA: bool = True
    EXPORT_DIR: str = "/app/exports"

    # Admin endpoint authentication
    ADMIN_SECRET: SecretStr = SecretStr("")

    # Startup Warmup
    WARMUP_ON_STARTUP: bool = True
    WARMUP_TIMEOUT_SECONDS: float = 110.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode='after')
    def check_secrets_safe(self):
        """Reject empty or known-weak placeholder credentials."""
        neo4j_pwd = self.NEO4J_PASSWORD.get_secret_value()
        if not neo4j_pwd or neo4j_pwd in _WEAK_PASSWORDS:
            raise ValueError(
                "[SECURITY] NEO4J_PASSWORD is missing or a known-weak placeholder. "
                "Set a strong password via the NEO4J_PASSWORD or NEO4J_PASS env var."
            )

        litellm_key = self.LITELLM_MASTER_KEY.get_secret_value()
        if not litellm_key or litellm_key in _WEAK_PASSWORDS:
            raise ValueError(
                "[SECURITY] LITELLM_MASTER_KEY is missing or a known-weak placeholder. "
                "Set it via the LITELLM_MASTER_KEY env var."
            )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance (reads .env once at startup)."""
    return Settings()
