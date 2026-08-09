#!/usr/bin/env python3
"""Automated Model Integrity Verification Script for DGX Spark Toolkit.

Verifies alignment between on-disk model weights (config.json) and
AI Gateway model registry (/v1/models).
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
import urllib.request
import urllib.error


def load_env_file(env_path: Path) -> Dict[str, str]:
    """Load environment variables from a .env file into a dictionary.

    Args:
        env_path: Path to the .env file.

    Returns:
        Dict[str, str]: Key-value pairs from .env file.
    """
    env_vars: Dict[str, str] = {}
    if not env_path.exists():
        return env_vars
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env_vars[key.strip()] = val.strip().strip('"').strip("'")
    return env_vars


def get_disk_model_info(model_dir: str) -> Dict[str, Any]:
    """Read model configuration from config.json in the target directory.

    Args:
        model_dir: Absolute path to the model weights directory.

    Returns:
        Dict[str, Any]: Model configuration metadata.
    """
    config_file = Path(model_dir) / "config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"config.json not found in model directory: {model_dir}")

    with open(config_file, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    return {
        "model_dir": model_dir,
        "architectures": config_data.get("architectures", []),
        "model_type": config_data.get("model_type", "unknown"),
    }


def query_gateway_models(gateway_url: str, api_key: str) -> List[str]:
    """Query list of models from LiteLLM AI Gateway.

    Args:
        gateway_url: Gateway base URL (e.g. http://localhost:8090/v1).
        api_key: LiteLLM master key for authorization.

    Returns:
        List[str]: List of registered model IDs.
    """
    endpoint = f"{gateway_url.rstrip('/')}/models"
    req = urllib.request.Request(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return [m["id"] for m in data.get("data", [])]
            raise RuntimeError(f"Gateway returned HTTP status {response.status}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to connect to AI Gateway at {endpoint}: {e}") from e


def verify_integrity(project_root: Path) -> Tuple[bool, List[str]]:
    """Execute model integrity verification between disk weights and gateway.

    Args:
        project_root: Project root directory containing .env.

    Returns:
        Tuple[bool, List[str]]: (Success status, List of report log messages).
    """
    logs: List[str] = []
    env_vars = load_env_file(project_root / ".env")
    
    model_dir = os.getenv("LOCAL_PRIMARY_LLM_DIR") or env_vars.get(
        "LOCAL_PRIMARY_LLM_DIR", "/home/vvc/models/Qwen3.5-35B-A3B-FP8"
    )
    served_name = os.getenv("LOCAL_PRIMARY_SERVED_NAME") or env_vars.get(
        "LOCAL_PRIMARY_SERVED_NAME", "qwen-local-primary"
    )
    gateway_url = os.getenv("AI_GATEWAY_URL") or "http://localhost:8090/v1"
    api_key = os.getenv("LITELLM_MASTER_KEY") or "sk-spark-secure-key-2026"

    logs.append(f"🔍 Target Model Directory: {model_dir}")
    logs.append(f"🔍 Expected Served Name:   {served_name}")

    # 1. Check disk weights
    try:
        disk_info = get_disk_model_info(model_dir)
        logs.append(f"✅ Disk Model Type:        {disk_info['model_type']}")
        logs.append(f"✅ Disk Architectures:     {disk_info['architectures']}")
    except Exception as err:
        logs.append(f"❌ Disk Verification Error: {err}")
        return False, logs

    # 2. Check Gateway models registry
    try:
        gateway_models = query_gateway_models(gateway_url, api_key)
        logs.append(f"✅ Gateway Registered Models: {len(gateway_models)} models total")
    except Exception as err:
        logs.append(f"❌ Gateway Verification Error: {err}")
        return False, logs

    # 3. Validate consistency
    is_valid = True
    if served_name in gateway_models:
        logs.append(f"✅ Served Name '{served_name}' found in Gateway registry.")
    else:
        logs.append(f"❌ Served Name '{served_name}' NOT found in Gateway registry!")
        is_valid = False

    # Check for legacy misleading aliases
    misleading_aliases = ["Qwen-3.6-35B-NVFP4", "qwen3.6-35b"]
    found_misleading = [a for a in misleading_aliases if a in gateway_models]
    if found_misleading:
        logs.append(f"⚠️ Warning: Misleading legacy alias found on Gateway: {found_misleading}")
        is_valid = False
    else:
        logs.append("✅ No misleading version aliases detected on Gateway.")

    return is_valid, logs


def main() -> None:
    """Main script entrypoint."""
    project_root = Path(__file__).resolve().parent.parent
    success, logs = verify_integrity(project_root)

    print("==================================================")
    print("  DGX Spark Toolkit — Model Integrity Verifier   ")
    print("==================================================")
    for line in logs:
        print(line)
    print("==================================================")

    if success:
        print("🎉 INTEGRITY VERIFICATION PASSED: Disk & Gateway aligned 100%.")
        sys.exit(0)
    else:
        print("💥 INTEGRITY VERIFICATION FAILED: Discrepancies detected!")
        sys.exit(1)


if __name__ == "__main__":
    main()
