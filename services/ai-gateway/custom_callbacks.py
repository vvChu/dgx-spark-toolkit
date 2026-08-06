import os
import sys
from litellm.integrations.custom_logger import CustomLogger

class GeminiParameterCorrector(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, data, *args, **kwargs):
        try:
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
            if "lite" in model.lower() or "embedding" in model.lower() or "embed" in model.lower():
                should_correct = False
                
                # Make sure to strip any thinking parameters so it doesn't fail
                if "thinking_budget" in data: del data["thinking_budget"]
                if "thinking_level" in data: del data["thinking_level"]
                if "extra_body" in data and isinstance(data["extra_body"], dict):
                    if "thinking_budget" in data["extra_body"]: del data["extra_body"]["thinking_budget"]
                    if "thinking_level" in data["extra_body"]: del data["extra_body"]["thinking_level"]
                    if "generationConfig" in data["extra_body"] and isinstance(data["extra_body"]["generationConfig"], dict):
                        if "thinking_config" in data["extra_body"]["generationConfig"] and isinstance(data["extra_body"]["generationConfig"]["thinking_config"], dict):
                            if "thinking_budget" in data["extra_body"]["generationConfig"]["thinking_config"]:
                                del data["extra_body"]["generationConfig"]["thinking_config"]["thinking_budget"]
                            if "thinking_level" in data["extra_body"]["generationConfig"]["thinking_config"]:
                                del data["extra_body"]["generationConfig"]["thinking_config"]["thinking_level"]

            if should_correct:
                # Remove thinking_budget if present to avoid 400 Bad Request
                if "thinking_budget" in data:
                    del data["thinking_budget"]
                
                if "extra_body" in data and isinstance(data["extra_body"], dict):
                    if "thinking_budget" in data["extra_body"]:
                        del data["extra_body"]["thinking_budget"]
                    if "generationConfig" in data["extra_body"] and isinstance(data["extra_body"]["generationConfig"], dict):
                        if "thinking_config" in data["extra_body"]["generationConfig"] and isinstance(data["extra_body"]["generationConfig"]["thinking_config"], dict):
                            if "thinking_budget" in data["extra_body"]["generationConfig"]["thinking_config"]:
                                del data["extra_body"]["generationConfig"]["thinking_config"]["thinking_budget"]

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
                    else:
                        thinking_level = "medium"

                # 3. Ensure the thinking_level is set in the correct place for Google API
                # Google API expects it in generationConfig.thinking_config.thinking_level
                if "extra_body" not in data or not isinstance(data["extra_body"], dict):
                    data["extra_body"] = {}
                
                if "generationConfig" not in data["extra_body"] or not isinstance(data["extra_body"]["generationConfig"], dict):
                    data["extra_body"]["generationConfig"] = {}
                
                if "thinking_config" not in data["extra_body"]["generationConfig"] or not isinstance(data["extra_body"]["generationConfig"]["thinking_config"], dict):
                    data["extra_body"]["generationConfig"]["thinking_config"] = {}

                data["extra_body"]["generationConfig"]["thinking_config"]["thinking_level"] = thinking_level
                data["extra_body"]["generationConfig"]["thinking_config"]["include_thoughts"] = True

                # 4. Clean up temperature/top_p if they are default to avoid warnings
                # In Gemini 3.x, sampling parameters are discouraged.
                if "temperature" in data and data["temperature"] in [1.0, 0.0]:
                    del data["temperature"]
                if "top_p" in data and data["top_p"] in [1.0]:
                    del data["top_p"]

                sys.stdout.write(f"[GeminiCorrector] Corrected model '{model}': thinking_level set to '{thinking_level}' (thinking_budget '{thinking_budget}' removed)\n")
                sys.stdout.flush()

        except Exception as e:
            sys.stderr.write(f"[GeminiCorrector] Error during pre-call parameter correction: {e}\n")
            sys.stderr.flush()
        
        return data

# Create single instance
gemini_corrector_instance = GeminiParameterCorrector()
