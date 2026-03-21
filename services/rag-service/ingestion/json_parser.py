"""Robust JSON extraction from LLM responses.

Handles chain-of-thought, markdown code blocks, and noisy Qwen 3.5 output.
"""
import json
import re

from ingestion.cleaning_utils import clean_llm_text


def extract_json_from_response(data):
    """Robustly extract JSON from Qwen 3.5 API response.

    Qwen 3.5 with reasoning-parser often outputs a long chain-of-thought
    before the actual JSON. This function handles all common patterns:
    - JSON inside ```json ... ``` markdown blocks
    - JSON inside ``` ... ``` blocks
    - Raw JSON objects {} anywhere in the response
    - JSON with JS-style comments
    """
    if not isinstance(data, dict) or "choices" not in data or not data["choices"]:
        raise ValueError(f"Invalid API response structure: {data}")

    choice = data["choices"][0]
    if not isinstance(choice, dict):
        raise ValueError(f"Invalid choice structure: {choice}")

    msg = choice.get("message", {})
    content = msg.get("content") or ""
    if not content.strip():
        content = msg.get("reasoning_content") or ""

    content = content.strip()
    if not content:
        raise ValueError("Empty response from LLM")

    # PRE-PROCESSING: Use robust global cleaning to remove thoughts and noise
    content = clean_llm_text(content)

    # Strategy 1: Find JSON inside markdown code blocks (most reliable)
    json_blocks = re.findall(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', content)
    if json_blocks:
        actual_blocks = [b for b in json_blocks if "..." not in b]
        json_str = actual_blocks[-1] if actual_blocks else json_blocks[-1]
        json_str = re.sub(r'//.*?$|/\*.*?\*/', '', json_str, flags=re.MULTILINE)
        try:
            return json.loads(json_str.strip())
        except json.JSONDecodeError:
            pass

    # Strategy 2: Find the LAST standalone JSON object {} in the text
    all_objects = re.findall(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', content)
    if all_objects:
        data_objects = [obj for obj in all_objects if "..." not in obj]
        search_list = reversed(data_objects) if data_objects else reversed(all_objects)

        for obj_str in search_list:
            obj_str = re.sub(r'//.*?$|/\*.*?\*/', '', obj_str, flags=re.MULTILINE)
            try:
                return json.loads(obj_str.strip())
            except json.JSONDecodeError:
                continue

    # Strategy 3: Greedy — find the largest possible JSON substring
    first_brace = content.find('{')
    if first_brace != -1:
        last_brace = content.rfind('}')
        if last_brace > first_brace:
            candidate = content[first_brace:last_brace + 1]
            candidate = re.sub(r'//.*?$|/\*.*?\*/', '', candidate, flags=re.MULTILINE)
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                pass

    raise ValueError(f"No valid JSON found in response (check for truncation): {content[:300]}...")
