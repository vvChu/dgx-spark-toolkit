import sys
from litellm.integrations.custom_logger import CustomLogger


def _estimate_tokens_and_has_vision(messages):
    """Estimate token count and check for vision payloads in request messages."""
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


class GeminiParameterCorrector(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, data, *args, **kwargs):
        try:
            model = data.get("model", "")

            # 0. Token-Length Tiered Routing for generic text-auto or short requests
            # If text-only and < 500 tokens, route to Gemma 4 (14.4K RPD quota pool)
            if model in ["text-auto", "auto", "text-light-auto"]:
                est_tokens, has_vision = _estimate_tokens_and_has_vision(data.get("messages", []))
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

            # We target Gemini 3.x, 3.5+ models, and specific Gemini 2.5 reasoning models
            is_gemini_3_or_above = any(x in model for x in ["gemini-3.5", "gemini-3", "gemini-3.1"])

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
            # (e.g. gemini-2.5-flash-lite, gemini-embedding-2, etc.)
            # Note: gemini-3.5-flash-lite supports thinking_level ("minimal" or "low")
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

                # 2. Correct and map thinking_level if missing or if thinking_budget was provided
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

                # 3. Ensure the thinking_level is set in the correct place for Google API
                # Google API expects it in generationConfig.thinking_config.thinking_level
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

                # 4. Clean up temperature/top_p if they are default to avoid warnings
                # In Gemini 3.x, sampling parameters are discouraged.
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


# Create single instance
gemini_corrector_instance = GeminiParameterCorrector()
