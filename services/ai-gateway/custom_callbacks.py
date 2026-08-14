"""Custom callbacks and parameter normalization for LiteLLM Gateway.

Provides request parameter correction, thinking budget mapping, token-length tiered routing,
and API key cooldown management for Google Gemini & Gemma models.
"""
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from litellm.integrations.custom_logger import CustomLogger
except ImportError:
    class CustomLogger:  # type: ignore[no-redef]
        """Fallback base class when litellm is not installed in the local test runner."""
        pass


def _estimate_tokens_and_has_vision(messages: Any) -> Tuple[int, bool]:
    """Estimate token count and check for vision payloads in request messages."""
    return ParameterNormalizer.estimate_tokens_and_has_vision(messages)


class KeyCooldownManager:
    """Manages API key cooldowns and rotation upon encountering HTTP 429 Rate Limits."""

    def __init__(self, cooldown_seconds: int = 60) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._cooldown_dict: Dict[str, float] = {}  # In-memory fallback: api_key -> expiry_timestamp
        self._keys_pool: List[str] = []
        self._refresh_pool()

    def _refresh_pool(self) -> None:
        self._keys_pool = [
            os.getenv(f"GEMINI_API_KEY_{i}", "") for i in range(2, 12)
        ]
        self._keys_pool = [k for k in self._keys_pool if k]

    def is_key_in_cooldown(self, api_key: str) -> bool:
        if not api_key:
            return False
        expiry = self._cooldown_dict.get(api_key, 0.0)
        if time.time() < expiry:
            return True
        elif api_key in self._cooldown_dict:
            del self._cooldown_dict[api_key]
        return False

    def mark_key_cooldown(self, api_key: str) -> None:
        if not api_key:
            return
        self._cooldown_dict[api_key] = time.time() + self.cooldown_seconds
        short_key = f"...{api_key[-4:]}" if len(api_key) > 4 else api_key
        sys.stdout.write(f"[KeyCooldownManager] Key '{short_key}' placed on {self.cooldown_seconds}s cooldown (HTTP 429)\n")
        sys.stdout.flush()

    def get_available_key(self, current_key: str = "") -> str:
        self._refresh_pool()
        if not self._keys_pool:
            return current_key
        for k in self._keys_pool:
            if not self.is_key_in_cooldown(k):
                return k
        return self._keys_pool[0]


key_cooldown_manager = KeyCooldownManager(cooldown_seconds=60)


class ParameterNormalizer:
    """Pure domain module for request parameter correction and tiered routing."""

    @staticmethod
    def estimate_tokens_and_has_vision(messages: Any) -> Tuple[int, bool]:
        """Estimate token count (~4 chars/token) and detect image/vision payload parts."""
        total_chars = 0
        has_vision = False
        if not isinstance(messages, list):
            return 0, False
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") in ["image_url", "image", "inline_data"]:
                            has_vision = True
                        text = part.get("text", "")
                        total_chars += len(text)
        return total_chars // 4, has_vision

    @classmethod
    def normalize_request(cls, data: Dict[str, Any], cooldown_manager: Optional[KeyCooldownManager] = None) -> Dict[str, Any]:
        """Normalize model parameters, thinking configurations, and apply tiered routing."""
        try:
            model = data.get("model", "")

            # 0. Check API Key rotation if current key is in cooldown
            if cooldown_manager is not None:
                current_api_key = data.get("api_key", "")
                if current_api_key and cooldown_manager.is_key_in_cooldown(current_api_key):
                    available_key = cooldown_manager.get_available_key(current_api_key)
                    if available_key != current_api_key:
                        data["api_key"] = available_key
                        sys.stdout.write(
                            f"[KeyRotation] Current key in cooldown -> Rotated to next available key (...{available_key[-4:]})\n"
                        )
                        sys.stdout.flush()

            # 1. Token-Length Tiered Routing for generic text-auto or short requests
            if model in ["text-auto", "auto", "text-light-auto"]:
                est_tokens, has_vision = cls.estimate_tokens_and_has_vision(data.get("messages", []))
                if not has_vision and est_tokens < 500:
                    data["model"] = "openai/gemma-4-26b-a4b-it"
                    sys.stdout.write(
                        f"[TieredRouter] Short text prompt (~{est_tokens} tokens) -> Routed to Gemma 4 (14.4K RPD)\n"
                    )
                    sys.stdout.flush()
                else:
                    data["model"] = "gemini/gemini-3.5-flash-lite"
                    sys.stdout.write(
                        f"[TieredRouter] Long text/vision prompt (~{est_tokens} tokens) -> Routed to Gemini 3.5 Flash Lite\n"
                    )
                    sys.stdout.flush()
                model = data.get("model", "")

            # 2. Target Gemini 3.x, 3.5+ models, and specific Gemini 2.5 reasoning models
            is_gemini_3_or_above = any(x in model for x in ["gemini-3.7", "gemini-3.6", "gemini-3.5", "gemini-3", "gemini-3.1"])

            # Retrieve client's parameters
            thinking_budget = data.get("thinking_budget") or data.get("extra_body", {}).get("thinking_budget")
            thinking_level = data.get("thinking_level") or data.get("extra_body", {}).get("thinking_level")

            # Check inside generationConfig or thinking_config if any
            gen_config = data.get("generationConfig") or data.get("extra_body", {}).get("generationConfig", {})
            if not thinking_budget and isinstance(gen_config, dict):
                thinking_budget = gen_config.get("thinking_config", {}).get("thinking_budget")
            if not thinking_level and isinstance(gen_config, dict):
                thinking_level = gen_config.get("thinking_config", {}).get("thinking_level")

            # Determine if we should apply parameter correction:
            should_correct = (thinking_budget is not None) or (thinking_level is not None) or is_gemini_3_or_above

            # Explicitly exclude non-reasoning models from receiving default thinking parameters
            is_35_lite = ("gemini-3.5" in model.lower() or "gemini-3" in model.lower()) and "lite" in model.lower()
            if "embedding" in model.lower() or "embed" in model.lower() or ("lite" in model.lower() and not is_35_lite):
                should_correct = False

                # Make sure to strip any thinking parameters so it doesn't fail
                if "thinking_budget" in data:
                    del data["thinking_budget"]
                if "thinking_level" in data:
                    del data["thinking_level"]
                if "extra_body" in data and isinstance(data["extra_body"], dict):
                    if "thinking_budget" in data["extra_body"]:
                        del data["extra_body"]["thinking_budget"]
                    if "thinking_level" in data["extra_body"]:
                        del data["extra_body"]["thinking_level"]
                    if "generationConfig" in data["extra_body"] and isinstance(data["extra_body"]["generationConfig"], dict):
                        tc = data["extra_body"]["generationConfig"].get("thinking_config")
                        if isinstance(tc, dict):
                            tc.pop("thinking_budget", None)
                            tc.pop("thinking_level", None)

            if should_correct:
                # Remove thinking_budget if present to avoid 400 Bad Request
                if "thinking_budget" in data:
                    del data["thinking_budget"]

                if "extra_body" in data and isinstance(data["extra_body"], dict):
                    if "thinking_budget" in data["extra_body"]:
                        del data["extra_body"]["thinking_budget"]
                    gen_cfg = data["extra_body"].get("generationConfig")
                    if isinstance(gen_cfg, dict):
                        tc = gen_cfg.get("thinking_config")
                        if isinstance(tc, dict):
                            tc.pop("thinking_budget", None)

                # Correct and map thinking_level if missing or if thinking_budget was provided
                if not thinking_level and thinking_budget:
                    try:
                        tb = int(thinking_budget)
                        if tb <= 0:
                            thinking_level = "minimal"
                        elif tb <= 2048:
                            thinking_level = "low"
                        elif tb <= 8192:
                            thinking_level = "medium"
                        else:
                            thinking_level = "high"
                    except ValueError:
                        thinking_level = "medium"

                # Determine default thinking level based on model type if still missing
                if not thinking_level:
                    if "medium" in model:
                        thinking_level = "medium"
                    elif "high" in model:
                        thinking_level = "high"
                    elif "low" in model:
                        thinking_level = "low"
                    elif is_35_lite:
                        thinking_level = "minimal"
                    else:
                        thinking_level = "medium"

                # Ensure the thinking_level is set in the correct place for Google API
                if "extra_body" not in data or not isinstance(data["extra_body"], dict):
                    data["extra_body"] = {}

                extra = data["extra_body"]
                if "generationConfig" not in extra or not isinstance(extra["generationConfig"], dict):
                    extra["generationConfig"] = {}

                g_cfg = extra["generationConfig"]
                if "thinking_config" not in g_cfg or not isinstance(g_cfg["thinking_config"], dict):
                    g_cfg["thinking_config"] = {}

                g_cfg["thinking_config"]["thinking_level"] = thinking_level
                g_cfg["thinking_config"]["include_thoughts"] = True

                if "temperature" in data and data["temperature"] in [1.0, 0.0]:
                    del data["temperature"]
                if "top_p" in data and data["top_p"] in [1.0]:
                    del data["top_p"]

                sys.stdout.write(
                    f"[GeminiCorrector] Corrected model '{model}': thinking_level set to '{thinking_level}'\n"
                )
                sys.stdout.flush()

        except Exception as e:
            sys.stderr.write(f"[GeminiCorrector] Error during pre-call parameter correction: {e}\n")
            sys.stderr.flush()

        return data


class GeminiParameterCorrector(CustomLogger):
    """LiteLLM custom logger adapter delegating to ParameterNormalizer and KeyCooldownManager."""

    async def async_pre_call_hook(self, user_api_key_dict: Any, data: Dict[str, Any], *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Pre-call hook invoked by LiteLLM before forwarding request to upstream LLM."""
        return ParameterNormalizer.normalize_request(data, cooldown_manager=key_cooldown_manager)

    async def async_log_failure_event(self, kwargs: Dict[str, Any], response_obj: Any, start_time: Any, end_time: Any) -> None:
        """Intercept 429 Rate Limits and trigger key cooldown."""
        try:
            status_code = kwargs.get("status_code") or getattr(response_obj, "status_code", None)
            exception_str = str(kwargs.get("exception", "")).lower()
            if status_code == 429 or "429" in exception_str or "resource_exhausted" in exception_str:
                api_key = kwargs.get("api_key") or kwargs.get("litellm_params", {}).get("api_key", "")
                if api_key:
                    key_cooldown_manager.mark_key_cooldown(api_key)
        except Exception as e:
            sys.stderr.write(f"[KeyCooldownManager] Error in failure logging: {e}\n")
            sys.stderr.flush()


# Create single instance for LiteLLM callback registry
gemini_corrector_instance = GeminiParameterCorrector()
