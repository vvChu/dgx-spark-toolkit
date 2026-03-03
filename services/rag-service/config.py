from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Milvus Configuration
    MILVUS_HOST: str = "milvus-standalone"
    MILVUS_PORT: str = "19530"
    MILVUS_COLLECTION: str = "iso_19650_docs"

    # Model Configuration
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # AI Gateway Configuration (LiteLLM proxy — routes to vLLM + cloud)
    # Uses gateway instead of direct vLLM for fallback support and model flexibility
    VLLM_API_BASE: str = "http://ai-gateway:4000/v1"
    VLLM_MODEL: str = "qwen3.5-35b"
    LITELLM_MASTER_KEY: str = "sk-spark-secure-key-2026"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
