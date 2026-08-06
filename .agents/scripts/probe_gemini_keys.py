#!/usr/bin/env python3
"""Probe Google Gemini API keys — check validity, available models, and rate limit headers.

What this can detect:
  ✅ Key valid / revoked / forbidden
  ✅ Models accessible per key (from /v1beta/models list)
  ✅ Rate limit info from response headers (if Google returns them)
  ✅ Actual latency per key (useful for latency-based routing)
  ❌ RPD quota remaining — Google does NOT expose this via API

Usage:
    python3 .agents/scripts/probe_gemini_keys.py
    python3 .agents/scripts/probe_gemini_keys.py --env /path/to/.env
"""

import argparse
import os
import re
import time
import httpx

# ── Config ──────────────────────────────────────────────────────────────────
MODELS_OF_INTEREST = {
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemma-3-27b-it",
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
}

GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Minimal test prompt — cheap, fast, deterministic
TEST_PAYLOAD = {
    "contents": [{"parts": [{"text": "Reply with the single word: OK"}]}],
    "generationConfig": {"maxOutputTokens": 5, "temperature": 0.0},
}

TEST_MODEL = "gemini-3.1-flash-lite-preview"  # fastest for probe


# ── Helpers ─────────────────────────────────────────────────────────────────

def load_env(env_path: str) -> dict:
    """Parse .env file and return key→value dict."""
    env = {}
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                # Strip inline comments
                key, _, val = line.partition("=")
                val = val.split("#")[0].strip().strip('"').strip("'")
                env[key.strip()] = val
    except FileNotFoundError:
        pass
    return env


def get_gemini_keys(env: dict) -> list[tuple[str, str]]:
    """Extract all GEMINI_API_KEY_* entries sorted by key name."""
    keys = []
    # Include base key (GEMINI_API_KEY) and numbered ones
    for var_name in sorted(env.keys()):
        if re.match(r'^GEMINI_API_KEY(_\d+)?$', var_name):
            val = env[var_name]
            if val and len(val) > 10:
                keys.append((var_name, val))
    return keys


def list_models(api_key: str, client: httpx.Client) -> tuple[list[str], str]:
    """Call /v1beta/models to get models available for this key.

    Returns (model_names_of_interest, error_string_or_empty)
    """
    try:
        resp = client.get(
            f"{GOOGLE_API_BASE}/models",
            params={"key": api_key},
            timeout=10,
        )
        if resp.status_code == 403:
            return [], "403 FORBIDDEN (key revoked/invalid)"
        if resp.status_code == 429:
            return [], "429 RATE LIMITED (quota exceeded)"
        if resp.status_code != 200:
            return [], f"HTTP {resp.status_code}: {resp.text[:100]}"

        data = resp.json()
        all_names = {
            m.get("name", "").replace("models/", "")
            for m in data.get("models", [])
        }
        matched = sorted(all_names & MODELS_OF_INTEREST)
        return matched, ""
    except Exception as e:
        return [], f"ERROR: {e}"


def probe_key(api_key: str, client: httpx.Client) -> dict:
    """Send a minimal inference request and return timing + header info."""
    url = f"{GOOGLE_API_BASE}/models/{TEST_MODEL}:generateContent"
    t0 = time.time()
    try:
        resp = client.post(
            url,
            params={"key": api_key},
            json=TEST_PAYLOAD,
            timeout=15,
        )
        elapsed = time.time() - t0

        # Extract rate-limit headers (Google may return these)
        headers = dict(resp.headers)
        rl_headers = {
            k: v for k, v in headers.items()
            if any(x in k.lower() for x in ["x-ratelimit", "retry-after", "x-quota"])
        }

        if resp.status_code == 200:
            content = resp.json().get("candidates", [{}])[0]
            text = content.get("content", {}).get("parts", [{}])[0].get("text", "")
            return {
                "status": "OK",
                "latency_ms": round(elapsed * 1000),
                "response": text.strip()[:50],
                "rl_headers": rl_headers,
            }
        elif resp.status_code == 429:
            retry_after = resp.headers.get("retry-after", "unknown")
            return {
                "status": "RATE_LIMITED",
                "latency_ms": round(elapsed * 1000),
                "retry_after": retry_after,
                "rl_headers": rl_headers,
            }
        elif resp.status_code == 403:
            return {"status": "REVOKED", "latency_ms": round(elapsed * 1000)}
        else:
            return {
                "status": f"HTTP_{resp.status_code}",
                "latency_ms": round(elapsed * 1000),
                "body": resp.text[:100],
            }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Probe Gemini API keys")
    parser.add_argument("--env", default="/home/vvc/Codebase/dgx-spark-toolkit/.env",
                        help="Path to .env file")
    parser.add_argument("--models-only", action="store_true",
                        help="Only list models, skip inference probe")
    parser.add_argument("--skip-revoked", action="store_true",
                        help="Skip inference probe for keys that fail models check")
    args = parser.parse_args()

    env = load_env(args.env)
    # Also read from environment (Docker/shell exports)
    for k, v in os.environ.items():
        if k.startswith("GEMINI_API_KEY"):
            env[k] = v

    keys = get_gemini_keys(env)
    if not keys:
        print("❌ No GEMINI_API_KEY* found in .env or environment")
        return

    print(f"═══ Gemini API Key Probe ═══")
    print(f"Found {len(keys)} key(s). Test model: {TEST_MODEL}")
    print(f"Models of interest: {', '.join(sorted(MODELS_OF_INTEREST))}")
    print()

    results = {}
    with httpx.Client(timeout=20) as client:
        for var_name, api_key in keys:
            mask = api_key[:8] + "..." + api_key[-4:]
            print(f"─── {var_name} ({mask}) ───")

            # Step 1: List available models
            models, err = list_models(api_key, client)
            if err:
                print(f"  📋 Models: {err}")
                results[var_name] = {"models": [], "error": err}
                if args.skip_revoked:
                    print()
                    continue
            else:
                print(f"  📋 Models available: {', '.join(models) if models else '(none of interest)'}")

            if args.models_only:
                results[var_name] = {"models": models}
                print()
                continue

            # Step 2: Inference probe
            probe = probe_key(api_key, client)
            status = probe["status"]
            latency = probe.get("latency_ms", "?")

            if status == "OK":
                print(f"  ✅ Status: OK | Latency: {latency}ms | Response: '{probe.get('response', '')}'")
            elif status == "RATE_LIMITED":
                print(f"  ⚠️  Status: RATE LIMITED | Retry-After: {probe.get('retry_after', '?')}s")
            elif status == "REVOKED":
                print(f"  ❌ Status: REVOKED/FORBIDDEN")
            else:
                print(f"  ❌ Status: {status} | {probe.get('error', probe.get('body', ''))}")

            if probe.get("rl_headers"):
                print(f"  📊 Rate-limit headers: {probe['rl_headers']}")

            results[var_name] = {"models": models, "probe": probe}
            print()

    # Summary
    print("═══ SUMMARY ═══")
    ok = [k for k, v in results.items() if v.get("probe", {}).get("status") == "OK"]
    rate_limited = [k for k, v in results.items() if v.get("probe", {}).get("status") == "RATE_LIMITED"]
    revoked = [k for k, v in results.items() if "REVOKED" in str(v.get("error", "")) or v.get("probe", {}).get("status") == "REVOKED"]
    errors = [k for k, v in results.items() if v.get("error") and "REVOKED" not in str(v.get("error", ""))]

    print(f"  ✅ OK: {len(ok)} — {ok}")
    if rate_limited:
        print(f"  ⚠️  Rate limited: {len(rate_limited)} — {rate_limited}")
    if revoked:
        print(f"  ❌ Revoked: {len(revoked)} — {revoked}")
    if errors:
        print(f"  🔴 Error: {len(errors)} — {errors}")
    print()
    print("NOTE: RPD (daily quota) remaining is NOT available via Google API.")
    print("      To see daily quota: https://aistudio.google.com → API keys → Usage")


if __name__ == "__main__":
    main()
