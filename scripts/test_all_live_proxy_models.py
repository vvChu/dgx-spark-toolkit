#!/usr/bin/env python3
"""
Test connectivity to ALL models available at Centralized API Proxy.
Dynamically retrieves live models from GET /models and tests chat completions concurrently.
"""

import concurrent.futures
import json
import os
import sys
import time
from typing import Any, Dict, List
import requests

WORKSPACE_DIR = "/home/vvc/Codebase/dgx-spark-toolkit"
ENV_PATH = os.path.join(WORKSPACE_DIR, ".env")


def load_env() -> Dict[str, str]:
    env_vars: Dict[str, str] = {}
    if not os.path.exists(ENV_PATH):
        return env_vars
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    return env_vars


def get_all_proxy_models(proxy_url: str, proxy_key: str) -> List[str]:
    headers = {"Authorization": f"Bearer {proxy_key}"}
    try:
        resp = requests.get(f"{proxy_url}/models", headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return sorted([m["id"] for m in data.get("data", []) if "id" in m])
        else:
            print(f"[!] Failed to get models: HTTP {resp.status_code} - {resp.text}", flush=True)
            return []
    except Exception as e:
        print(f"[!] Error connecting to proxy /models: {e}", flush=True)
        return []


def test_single_model(proxy_url: str, proxy_key: str, model_id: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {proxy_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{proxy_url}/chat/completions"
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
    }

    start_t = time.time()
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=8)
        latency_ms = int((time.time() - start_t) * 1000)
        status_code = resp.status_code

        if status_code == 200:
            data = resp.json()
            content = ""
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "").strip()
            return {
                "model": model_id,
                "status": "OK",
                "code": 200,
                "latency_ms": latency_ms,
                "detail": content[:40].replace("\n", " "),
            }
        else:
            err_msg = resp.text[:100].strip().replace("\n", " ")
            return {
                "model": model_id,
                "status": "ERROR",
                "code": status_code,
                "latency_ms": latency_ms,
                "detail": err_msg,
            }
    except requests.exceptions.Timeout:
        return {
            "model": model_id,
            "status": "TIMEOUT",
            "code": 408,
            "latency_ms": int((time.time() - start_t) * 1000),
            "detail": "Timeout (>8s)",
        }
    except Exception as e:
        return {
            "model": model_id,
            "status": "FAILED",
            "code": 0,
            "latency_ms": int((time.time() - start_t) * 1000),
            "detail": str(e)[:80],
        }


def main():
    env = load_env()
    proxy_url = env.get("GATEWAY_PROXY_URL", "http://100.83.192.30:8045/v1")
    proxy_key = env.get("GATEWAY_PROXY_KEY", "")

    if not proxy_key:
        print("[!] GATEWAY_PROXY_KEY not found in .env!", flush=True)
        sys.exit(1)

    print("=" * 75, flush=True)
    print("🔍 KIỂM TRA TOÀN DIỆN KẾT NỐI ĐẾN CENTRALIZED API PROXY", flush=True)
    print(f"Proxy URL : {proxy_url}", flush=True)
    print("=" * 75, flush=True)

    models = get_all_proxy_models(proxy_url, proxy_key)
    if not models:
        print("[!] Không tìm thấy model nào từ API Proxy.", flush=True)
        sys.exit(1)

    print(f"[*] Tìm thấy {len(models)} model. Đang kiểm tra đồng thời (10 workers, timeout 8s)...\n", flush=True)

    results: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_model = {
            executor.submit(test_single_model, proxy_url, proxy_key, m): m
            for m in models
        }
        for future in concurrent.futures.as_completed(future_to_model):
            res = future.result()
            results.append(res)
            icon = "✅" if res["status"] == "OK" else "❌"
            if res["code"] == 429:
                icon = "⚠️"
            elif res["status"] == "TIMEOUT":
                icon = "⏳"
            print(
                f"[{len(results):02d}/{len(models):02d}] {icon} {res['model']:<33} | Code: {res['code']:<3} | {res['latency_ms']:>5}ms | {res['detail']}",
                flush=True,
            )

    results.sort(key=lambda x: (0 if x["status"] == "OK" else 1, x["model"]))

    ok_list = [r for r in results if r["status"] == "OK"]
    err_list = [r for r in results if r["status"] != "OK"]

    print("\n" + "=" * 75, flush=True)
    print("📊 BÁO CÁO TỔNG KẾT KẾT NỐI API PROXY", flush=True)
    print("=" * 75, flush=True)
    print(f"Tổng số model kiểm tra : {len(results)}", flush=True)
    print(f"Thành công (HTTP 200)  : {len(ok_list)} ({len(ok_list)/len(results)*100:.1f}%)", flush=True)
    print(f"Lỗi / Timeout / Khác   : {len(err_list)}", flush=True)
    print("=" * 75, flush=True)

    # Save Markdown report
    report_md_path = os.path.join(WORKSPACE_DIR, "proxy_test_report.md")
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("# 📊 Báo Cáo Kiểm Tra Kết Nối Model Tại API Proxy\n\n")
        f.write(f"- **Thời gian kiểm tra**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **Proxy Endpoint**: `{proxy_url}`\n")
        f.write(f"- **Tổng số model**: {len(results)}\n")
        f.write(f"- **Thành công (200 OK)**: {len(ok_list)}\n")
        f.write(f"- **Lỗi / Timeout**: {len(err_list)}\n\n")

        f.write("## 1. Danh sách Model Kết Nối Thành Công (200 OK)\n\n")
        f.write("| STT | Model ID | Latency | Phản hồi mẫu |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for i, r in enumerate(ok_list, 1):
            f.write(f"| {i} | `{r['model']}` | {r['latency_ms']}ms | `{r['detail']}` |\n")

        f.write("\n## 2. Danh sách Model Không Khả Dụng / Lỗi\n\n")
        f.write("| STT | Model ID | HTTP Code | Latency | Chi tiết lỗi |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for i, r in enumerate(err_list, 1):
            f.write(f"| {i} | `{r['model']}` | {r['code']} | {r['latency_ms']}ms | {r['detail']} |\n")

    print(f"[✓] Đã lưu báo cáo Markdown đầy đủ tại: {report_md_path}", flush=True)

    # Save JSON report
    report_json_path = os.path.join(WORKSPACE_DIR, "proxy_test_report.json")
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "proxy_url": proxy_url,
                "total": len(results),
                "success_count": len(ok_list),
                "error_count": len(err_list),
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"[✓] Đã lưu dữ liệu JSON chi tiết tại: {report_json_path}", flush=True)


if __name__ == "__main__":
    main()
