#!/usr/bin/env python3
"""
Model Updater & Self-Healing Daemon for DGX Spark.
Audits live models from Google AI Studio Direct API and Centralized API Proxy,
auto-patches litellm_config.yaml, restarts ai-gateway, and sends alerts.
"""

import argparse
import datetime
import os
import re
import subprocess
from typing import Dict, List, Optional, Set, Tuple
import requests

WORKSPACE_DIR = "/home/vvc/Codebase/dgx-spark-toolkit"
ENV_PATH = os.path.join(WORKSPACE_DIR, ".env")
CONFIG_PATH = os.path.join(WORKSPACE_DIR, "services", "ai-gateway", "litellm_config.yaml")


def load_env() -> Dict[str, str]:
    """Loads key-value pairs from .env file."""
    env_vars: Dict[str, str] = {}
    if not os.path.exists(ENV_PATH):
        return env_vars
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()
    return env_vars


def send_telegram(token: str, chat_id: str, message: str) -> None:
    """Sends a markdown formatted alert to Telegram."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[!] Failed to send Telegram message: {e}")


def check_docker_logs_for_errors() -> bool:
    """Scans the last 5000 lines of ai-gateway logs for 404/400 errors related to models."""
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", "5000", "ai-gateway"],
            capture_output=True,
            text=True,
            check=True,
        )
        logs = result.stderr + result.stdout
        error_indicators = [
            ("NotFoundError" in logs and "404" in logs and "is not found for API version" in logs),
            ("model_not_found" in logs),
            ("Resource has been exhausted" in logs and "429" in logs),
        ]
        return any(error_indicators)
    except Exception as e:
        print(f"[!] Error checking docker logs: {e}")
        return False


def get_live_google_models(env: Dict[str, str]) -> List[str]:
    """Fetches active models from Google AI Studio using available GEMINI_API_KEYs."""
    keys = [v for k, v in env.items() if k.startswith("GEMINI_API_KEY") and v]
    if not keys:
        return []

    for api_key in keys:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        try:
            resp = requests.get(url, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                return [
                    m["name"].replace("models/", "")
                    for m in data.get("models", [])
                    if "name" in m
                ]
        except Exception:
            continue
    return []


def get_live_proxy_models(env: Dict[str, str]) -> List[str]:
    """Fetches available models from Centralized API Proxy."""
    proxy_url = env.get("GATEWAY_PROXY_URL", "http://100.83.192.30:8045/v1")
    proxy_key = env.get("GATEWAY_PROXY_KEY", "")
    if not proxy_key:
        return []

    try:
        resp = requests.get(
            f"{proxy_url}/models",
            headers={"Authorization": f"Bearer {proxy_key}"},
            timeout=8,
        )
        if resp.status_code == 200:
            return [m["id"] for m in resp.json().get("data", []) if "id" in m]
    except Exception as e:
        print(f"[!] Warning: Could not reach Centralized Proxy at {proxy_url}: {e}")
    return []


def find_gemma_replacement(conf_model: str, live_models: List[str]) -> Optional[str]:
    """Determines the best matching replacement for an obsolete Gemma model."""
    gemma_live = [m for m in live_models if "gemma" in m and "it" in m]
    if not gemma_live:
        return None

    if "27b" in conf_model or "31b" in conf_model:
        matches = [m for m in gemma_live if "31b" in m or "27b" in m]
        if matches:
            return matches[0]
    elif "12b" in conf_model or "26b" in conf_model:
        matches = [m for m in gemma_live if "26b" in m or "12b" in m]
        if matches:
            return matches[0]
    return gemma_live[0]


def audit_and_patch_config(
    live_google: List[str], live_proxy: List[str], apply_changes: bool = False
) -> Tuple[List[str], bool]:
    """Audits litellm_config.yaml against live models and optionally patches it."""
    if not os.path.exists(CONFIG_PATH):
        print(f"[!] Config file not found at {CONFIG_PATH}")
        return [], False

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = content
    patches_made: List[str] = []

    # 1. Audit Gemma models
    configured_gemma = set(
        re.findall(r"model:\s*openai/(gemma-[a-zA-Z0-9\-\.]+)", content)
    )
    for conf_model in configured_gemma:
        if conf_model not in live_google:
            replacement = find_gemma_replacement(conf_model, live_google)
            if replacement and replacement != conf_model:
                print(f"[PATCH] Gemma update: {conf_model} -> {replacement}")
                new_content = new_content.replace(
                    f"openai/{conf_model}", f"openai/{replacement}"
                )
                patches_made.append(f"`{conf_model}` ➡️ `{replacement}`")

    # 2. Audit Direct Gemini models
    configured_gemini = set(
        re.findall(r"model:\s*gemini/(gemini-[a-zA-Z0-9\-\.]+)", content)
    )
    for conf_model in configured_gemini:
        if conf_model not in live_google:
            print(f"[WARN] Configured Gemini model '{conf_model}' not found in live Google API list.")

    # 3. Audit & Auto-fix Claude Proxy Prefixes (must use openai/ with GATEWAY_PROXY_URL)
    invalid_anthropic_proxy = set(
        re.findall(r"model:\s*anthropic/(claude-[a-zA-Z0-9\-\.]+)", content)
    )
    for model_id in invalid_anthropic_proxy:
        print(f"[PATCH] Fixing Claude Proxy prefix: anthropic/{model_id} -> openai/{model_id}")
        new_content = new_content.replace(
            f"anthropic/{model_id}", f"openai/{model_id}"
        )
        patches_made.append(f"`anthropic/{model_id}` ➡️ `openai/{model_id}`")

    has_changes = len(patches_made) > 0
    if has_changes and apply_changes:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"[✓] Successfully patched {CONFIG_PATH}")

    return patches_made, has_changes


def restart_and_verify_gateway() -> bool:
    """Restarts the ai-gateway container and performs an endpoint health check."""
    print("[*] Restarting ai-gateway container...")
    try:
        subprocess.run(["docker", "restart", "ai-gateway"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Failed to restart ai-gateway: {e}")
        return False

    print("[*] Verifying gateway health...")
    import time
    time.sleep(4)
    try:
        resp = requests.post(
            "http://localhost:8090/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-spark-secure-key-2026",
                "Content-Type": "application/json",
            },
            json={
                "model": "ocr-primary",
                "messages": [{"role": "user", "content": "Health check"}],
            },
            timeout=10,
        )
        if resp.status_code == 200:
            print("[✓] AI Gateway health check passed (HTTP 200).")
            return True
        print(f"[!] AI Gateway health check returned HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[!] AI Gateway health check failed: {e}")
    return False


def run_audit_mode(live_google: List[str], live_proxy: List[str]) -> None:
    """Prints a structured audit report of all upstream providers."""
    print("\n" + "=" * 60)
    print("📊 AI GATEWAY LIVE MODEL AUDIT REPORT")
    print("=" * 60)
    print(f"\n[1] Google AI Studio Direct API ({len(live_google)} models available):")
    for m in sorted(live_google):
        if any(prefix in m for prefix in ["gemini", "gemma", "imagen", "veo"]):
            print(f"  • {m}")

    print(f"\n[2] Centralized API Proxy ({len(live_proxy)} models available):")
    for m in sorted(live_proxy):
        print(f"  • {m}")

    print("\n" + "=" * 60)


def main() -> None:
    """CLI Entrypoint for Model Auto-Updater."""
    parser = argparse.ArgumentParser(
        description="Audit and auto-update models for AI Gateway."
    )
    parser.add_argument(
        "--force", action="store_true", help="Force model audit and auto-patching."
    )
    parser.add_argument(
        "--audit", action="store_true", help="Audit live models without applying patches."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Check for patches without applying."
    )
    args = parser.parse_args()

    env = load_env()
    tg_token = env.get("TELEGRAM_BOT_TOKEN")
    tg_chat_id = env.get("TELEGRAM_CHAT_ID")

    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Model Updater starting...")

    # Fetch live models from providers
    live_google = get_live_google_models(env)
    live_proxy = get_live_proxy_models(env)

    if args.audit:
        run_audit_mode(live_google, live_proxy)
        audit_and_patch_config(live_google, live_proxy, apply_changes=False)
        return

    # Check whether we should proceed with patching
    should_patch = args.force
    if not should_patch and not args.dry_run:
        has_errors = check_docker_logs_for_errors()
        if not has_errors:
            print("[✓] No 404/400 model errors in recent docker logs. Gateway is healthy.")
            return
        print("[!] Detected model error in docker logs. Proceeding with auto-healing...")
        should_patch = True

    apply_changes = not args.dry_run
    patches, changed = audit_and_patch_config(
        live_google, live_proxy, apply_changes=apply_changes
    )

    if changed and apply_changes:
        success = restart_and_verify_gateway()
        if tg_token and tg_chat_id:
            status_text = "thành công" if success else "thất bại"
            msg = (
                f"🛠️ *DGX Spark Model Auto-Updater*\n\n"
                f"Đã cập nhật các model mới/sửa lỗi:\n"
                + "\n".join([f"- {p}" for p in patches])
                + f"\n\nKhởi động lại AI Gateway: *{status_text}*."
            )
            send_telegram(tg_token, tg_chat_id, msg)
            print("[✓] Sent Telegram notification.")
    elif not patches:
        print("[✓] Configuration is fully aligned with active upstream models. No patches needed.")


if __name__ == "__main__":
    main()
