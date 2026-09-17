#!/usr/bin/env python3
"""
Verify AI Gateway endpoints with correct master key and .env path.
"""
import os
import sys
import time
import requests

def main():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    master_key = ""
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("LITELLM_MASTER_KEY="):
                    master_key = line.split("=", 1)[1].strip()
                elif not master_key and line.startswith("GATEWAY_MASTER_KEY="):
                    master_key = line.split("=", 1)[1].strip()

    if not master_key:
        print("[!] Warning: Master key not found in .env, checking default...")
        master_key = "sk-spark-secure-key-2026"

    masked_key = master_key[:8] + "..." if len(master_key) > 8 else "***"
    print(f"Loaded Master Key: {masked_key}", flush=True)

    base_url = "http://localhost:8090"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {master_key}"
    }

    # 1. Health Check (liveliness)
    print(f"\n=== 1. Checking AI Gateway Health: {base_url}/health/liveliness ===", flush=True)
    try:
        t0 = time.time()
        r = requests.get(f"{base_url}/health/liveliness", headers=headers, timeout=5)
        dt = (time.time() - t0) * 1000
        print(f"Status: {r.status_code} ({dt:.1f}ms)", flush=True)
        print(f"Response: {r.text[:200]}", flush=True)
    except Exception as e:
        print(f"Error checking health: {e}", flush=True)

    # 2. Test claude-opus-4-6-thinking via Gateway
    print("\n=== 2. Testing claude-opus-4-6-thinking via Gateway ===", flush=True)
    payload_opus = {
        "model": "claude-opus-4-6-thinking",
        "messages": [{"role": "user", "content": "Hello! Confirm your name and that you are working in 1 short sentence."}],
        "max_tokens": 80
    }
    try:
        t0 = time.time()
        r = requests.post(f"{base_url}/v1/chat/completions", headers=headers, json=payload_opus, timeout=60)
        dt = time.time() - t0
        print(f"Status: {r.status_code} ({dt:.2f}s)", flush=True)
        if r.status_code == 200:
            data = r.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content", "")
            print(f"Result Content:\n{content.strip()}", flush=True)
            if "reasoning_content" in msg and msg["reasoning_content"]:
                print(f"Thinking Content (first 100 chars): {msg['reasoning_content'][:100]}...", flush=True)
        else:
            print(f"Error Response:\n{r.text}", flush=True)
    except Exception as e:
        print(f"Opus request failed: {e}", flush=True)

    # 3. Test gemini-3.8-flash via Gateway
    print("\n=== 3. Testing gemini-3.8-flash via Gateway ===", flush=True)
    payload_gemini = {
        "model": "gemini-3.8-flash",
        "messages": [{"role": "user", "content": "Xin chào, phản hồi 1 câu ngắn gọn xác nhận bạn là Gemini 3.8 Flash."}],
        "max_tokens": 60
    }
    try:
        t0 = time.time()
        r = requests.post(f"{base_url}/v1/chat/completions", headers=headers, json=payload_gemini, timeout=30)
        dt = time.time() - t0
        print(f"Status: {r.status_code} ({dt:.2f}s)", flush=True)
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"].get("content", "")
            print(f"Result Content:\n{content.strip()}", flush=True)
        else:
            print(f"Error Response:\n{r.text}", flush=True)
    except Exception as e:
        print(f"Gemini request failed: {e}", flush=True)

    # 4. Test Embedding with drop_params verification (Issue #51)
    print("\n=== 4. Testing Embedding with drop_params (encoding_format='base64') ===", flush=True)
    payload_embed = {
        "model": "gemini-embedding-2",
        "input": "Hệ thống trích xuất văn bản quy chuẩn xây dựng Việt Nam",
        "encoding_format": "base64"  # Unsupported by native Gemini; LiteLLM must drop it cleanly
    }
    try:
        t0 = time.time()
        r = requests.post(f"{base_url}/v1/embeddings", headers=headers, json=payload_embed, timeout=30)
        dt = time.time() - t0
        print(f"Status: {r.status_code} ({dt:.2f}s)", flush=True)
        if r.status_code == 200:
            data = r.json()
            embed_dim = len(data["data"][0]["embedding"]) if "data" in data and data["data"] else 0
            print(f"Success! Generated embedding vector length: {embed_dim}", flush=True)
        else:
            print(f"Error Response:\n{r.text}", flush=True)
    except Exception as e:
        print(f"Embedding request failed: {e}", flush=True)

    # 5. Test Canonical Stable Aliases (Issue #51)
    print("\n=== 5. Testing Canonical Stable Aliases ===", flush=True)
    aliases_to_test = [
        ("gemini-flash-latest", "/v1/chat/completions", {"model": "gemini-flash-latest", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 10}),
        ("gemini-reasoning-latest", "/v1/chat/completions", {"model": "gemini-reasoning-latest", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 10}),
        ("embedding-default", "/v1/embeddings", {"model": "embedding-default", "input": "test alias"}),
    ]
    for alias_name, endpoint, payload in aliases_to_test:
        try:
            t0 = time.time()
            r = requests.post(f"{base_url}{endpoint}", headers=headers, json=payload, timeout=30)
            dt = time.time() - t0
            print(f"Alias '{alias_name}' -> Status: {r.status_code} ({dt:.2f}s)", flush=True)
            if r.status_code != 200:
                print(f"  Error: {r.text[:150]}", flush=True)
        except Exception as e:
            print(f"Alias '{alias_name}' failed: {e}", flush=True)

if __name__ == "__main__":
    main()

