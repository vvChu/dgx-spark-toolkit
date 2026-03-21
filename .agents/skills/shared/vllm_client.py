"""
Shared vLLM Client for all AI Skills.
Routes through the AI Gateway (LiteLLM proxy) for unified model access,
fallbacks, and cloud model support. Supports all 25+ models via gateway.
"""

import base64
import os
import sys
import urllib.request
from urllib.parse import urlparse
import requests

# --- Configuration ---
# Routes through AI Gateway (LiteLLM) — supports local vLLM + cloud proxy + fallbacks
# Use VLLM_API_BASE to point at the gateway instead of raw vLLM port
VLLM_API_BASE = os.environ.get("VLLM_API_BASE", "http://host.docker.internal:8090/v1")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "rag-core")
GATEWAY_API_KEY = os.environ.get("LITELLM_MASTER_KEY", "")


def is_url(string: str) -> bool:
    """Check if a string is a valid URL."""
    try:
        result = urlparse(string)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def get_image_base64(image_source: str) -> str:
    """
    Read an image from a local file path or URL and return its base64-encoded string.
    """
    if is_url(image_source):
        print(f"[*] Downloading image from URL: {image_source}")
        try:
            req = urllib.request.Request(image_source, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                image_data = response.read()
                return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            print(f"[-] Failed to download: {e}")
            sys.exit(1)
    else:
        if not os.path.exists(image_source):
            print(f"[-] File not found: {image_source}")
            sys.exit(1)
        print(f"[*] Reading local image: {image_source}")
        try:
            with open(image_source, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"[-] Failed to read file: {e}")
            sys.exit(1)


def chat_completion(messages: list, temperature: float = 0.1, max_tokens: int = 2048,
                    model: str = None, api_base: str = None) -> str:
    """
    Send a chat completion request through the AI Gateway and return the assistant's content.
    Supports all gateway models: rag-core (local), rag-light (local), claude-sonnet-4-6, gemini-3-flash, gpt-4o, etc.
    """
    _model = model or VLLM_MODEL
    _base = api_base or VLLM_API_BASE
    url = f"{_base}/chat/completions"

    payload = {
        "model": _model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GATEWAY_API_KEY}"
    }

    response = requests.post(url, json=payload, headers=headers, timeout=600)
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content']
