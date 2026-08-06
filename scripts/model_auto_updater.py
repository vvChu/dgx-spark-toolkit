#!/usr/bin/env python3
"""
Self-Healing Model Updater Daemon for DGX Spark
Reads ai-gateway logs for 404 errors, checks Google API for available models,
patches litellm_config.yaml, restarts ai-gateway, and sends a Telegram alert.
"""

import os
import re
import subprocess
import requests
import datetime

WORKSPACE_DIR = "/home/vvc/Codebase/dgx-spark-toolkit"
ENV_PATH = os.path.join(WORKSPACE_DIR, ".env")
CONFIG_PATH = os.path.join(WORKSPACE_DIR, "services", "ai-gateway", "litellm_config.yaml")

def load_env():
    env_vars = {}
    if not os.path.exists(ENV_PATH):
        return env_vars
    with open(ENV_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()
    return env_vars

def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def check_docker_logs_for_errors():
    """Scans the last 5000 lines of ai-gateway logs for 404 errors related to models."""
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", "5000", "ai-gateway"],
            capture_output=True, text=True, check=True
        )
        logs = result.stderr + result.stdout
        # Look for the specific 404 error string from Google API
        if "NotFoundError" in logs and "404" in logs and "is not found for API version" in logs:
            return True
        return False
    except Exception as e:
        print(f"Error checking docker logs: {e}")
        return False

def get_live_google_models(api_key):
    """Fetches the list of available models from Google API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            if name.startswith("models/"):
                models.append(name.split("models/")[1])
        return models
    except Exception as e:
        print(f"Failed to fetch live models: {e}")
        return []

def auto_patch_config(live_models):
    """Reads config, checks for obsolete models, and patches them."""
    with open(CONFIG_PATH, "r") as f:
        content = f.read()

    # Find all currently configured gemma models in the config
    # Example: model: openai/gemma-3-27b-it
    configured_models = set(re.findall(r"model:\s*openai/(gemma-[a-zA-Z0-9\-\.]+)", content))
    
    patches_made = []
    new_content = content

    for conf_model in configured_models:
        if conf_model not in live_models:
            # It's obsolete. Let's find the best replacement.
            # We want to match the same family (e.g., 'gemma') and roughly the same tier.
            # For simplicity, if we see 'gemma', we pick the largest/latest gemma model.
            gemma_live = [m for m in live_models if "gemma" in m and "it" in m]
            
            replacement = None
            if "27b" in conf_model or "31b" in conf_model:
                # Top tier
                matches = [m for m in gemma_live if "31b" in m or "27b" in m]
                if matches: replacement = matches[0]
            elif "12b" in conf_model or "26b" in conf_model:
                # Mid tier
                matches = [m for m in gemma_live if "26b" in m or "12b" in m]
                if matches: replacement = matches[0]
            else:
                # Fallback to whatever is available
                if gemma_live: replacement = gemma_live[0]
                
            if replacement and replacement != conf_model:
                print(f"Patching: {conf_model} -> {replacement}")
                new_content = new_content.replace(f"openai/{conf_model}", f"openai/{replacement}")
                patches_made.append(f"`{conf_model}` ➡️ `{replacement}`")

    if patches_made:
        with open(CONFIG_PATH, "w") as f:
            f.write(new_content)
        return patches_made
    return []

def restart_gateway():
    print("Restarting ai-gateway...")
    subprocess.run(["docker", "restart", "ai-gateway"], check=True)

def main():
    env = load_env()
    google_api_key = env.get("GEMINI_API_KEY_2")
    tg_token = env.get("TELEGRAM_BOT_TOKEN")
    tg_chat_id = env.get("TELEGRAM_CHAT_ID")

    if not google_api_key:
        print("GEMINI_API_KEY_2 not found in .env")
        return

    print(f"[{datetime.datetime.now()}] Starting Auto Updater Daemon...")

    # 1. Check logs for 404 errors
    has_errors = check_docker_logs_for_errors()
    if not has_errors:
        print("No 404 model errors detected in recent logs. Everything is healthy.")
        return

    print("Detected 404 errors in logs. Proceeding to fetch live models...")

    # 2. Fetch live models
    live_models = get_live_google_models(google_api_key)
    if not live_models:
        print("Failed to fetch live models or list is empty.")
        return

    # 3. Patch config
    patches = auto_patch_config(live_models)

    # 4. Restart and Notify
    if patches:
        try:
            restart_gateway()
            
            msg = "🛠️ *DGX Spark Auto-Healing Triggered*\n\n"
            msg += "Phát hiện lỗi 404 Model Not Found từ Google API. Đã tự động vá lỗi:\n"
            for p in patches:
                msg += f"- {p}\n"
            msg += "\n✅ Đã khởi động lại AI Gateway thành công!"
            
            if tg_token and tg_chat_id:
                send_telegram(tg_token, tg_chat_id, msg)
                print("Telegram notification sent.")
        except Exception as e:
            print(f"Error during restart/notify: {e}")
    else:
        print("No matching patches could be made. Obsolete models might require manual mapping.")

if __name__ == "__main__":
    main()
