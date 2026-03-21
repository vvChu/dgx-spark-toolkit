"""Unit tests for core.config.Settings validation."""
import os
import pytest

# Ensure CI-safe credentials are set *before* any import triggers get_settings().
os.environ.setdefault("NEO4J_PASSWORD", "ci_test_placeholder_safe")
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-ci-test-placeholder-safe")

from core.config import Settings, _WEAK_PASSWORDS


# ── Helper ──────────────────────────────────────────────────────────────
def _make_settings(**overrides):
    """Build a Settings instance with safe defaults merged with overrides."""
    defaults = {
        "NEO4J_PASSWORD": "strong_safe_password_1",
        "LITELLM_MASTER_KEY": "sk-strong-safe-key-2",
    }
    defaults.update(overrides)
    return Settings(**defaults)


# ── Security Validator ──────────────────────────────────────────────────
class TestSecurityValidator:
    def test_weak_neo4j_password_rejected(self):
        for weak in list(_WEAK_PASSWORDS)[:3]:
            with pytest.raises(ValueError, match="NEO4J_PASSWORD"):
                _make_settings(NEO4J_PASSWORD=weak)

    def test_empty_neo4j_password_rejected(self):
        with pytest.raises(ValueError, match="NEO4J_PASSWORD"):
            _make_settings(NEO4J_PASSWORD="")

    def test_weak_litellm_key_rejected(self):
        for weak in list(_WEAK_PASSWORDS)[:3]:
            with pytest.raises(ValueError, match="LITELLM_MASTER_KEY"):
                _make_settings(LITELLM_MASTER_KEY=weak)

    def test_valid_credentials_accepted(self):
        s = _make_settings()
        assert s.NEO4J_PASSWORD.get_secret_value() == "strong_safe_password_1"
        assert s.LITELLM_MASTER_KEY.get_secret_value() == "sk-strong-safe-key-2"


# ── Alias ───────────────────────────────────────────────────────────────
class TestAliases:
    def test_neo4j_pass_alias(self):
        """The legacy NEO4J_PASS env var should be accepted."""
        s = Settings(
            NEO4J_PASS="via_alias_password",
            LITELLM_MASTER_KEY="sk-strong-safe-key-2",
        )
        assert s.NEO4J_PASSWORD.get_secret_value() == "via_alias_password"


# ── Defaults ────────────────────────────────────────────────────────────
class TestDefaults:
    def test_default_values(self):
        s = _make_settings()
        assert s.MILVUS_COLLECTION == "legal_docs_v9"
        assert s.MILVUS_PORT == 19530
        assert s.GPU_ENABLED is True
        assert s.ENABLE_HYDE is False
        assert s.REDIS_URL == "redis://litellm-redis:6379/1"
        assert s.FORCE_CPU_RERANKER is False
        assert s.FORCE_CPU_EMBEDDING is False
        assert s.PDF_DIR == "/app/data/pdf"
        assert s.CORS_ALLOWED_ORIGINS == "http://localhost:5173"
        assert s.SEMANTIC_CACHE_THRESHOLD == 0.92

    def test_extra_fields_ignored(self):
        """Unknown env vars should not raise (extra='ignore')."""
        s = _make_settings(UNKNOWN_FUTURE_VAR="hello")
        assert not hasattr(s, "UNKNOWN_FUTURE_VAR")
