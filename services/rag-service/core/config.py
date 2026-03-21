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
    MILVUS_COLLECTION: str = "legal_docs_v9"

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

    # Semantic cache tuning — exposed here so they can be adjusted via env without rebuilding
    ENABLE_SEMANTIC_CACHE: bool = True
    SEMANTIC_CACHE_THRESHOLD: float = 0.92
    SEMANTIC_CACHE_TTL_SECONDS: int = 3600

    # Telegram Notifications
    TELEGRAM_BOT_TOKEN: SecretStr = SecretStr("")
    TELEGRAM_CHAT_ID: str = ""

    # Data Export Settings
    EXPORT_PROCESSED_DATA: bool = True
    EXPORT_DIR: str = "/app/exports"

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
