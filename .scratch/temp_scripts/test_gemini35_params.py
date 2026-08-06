import os
import urllib.request
import urllib.error
import json
import socket
import sys

API_KEY_LOCAL = os.getenv("LITELLM_MASTER_KEY", "sk-spark-secure-key-2026")
BASE_URL_LOCAL = "http://127.0.0.1:8090/v1"

API_KEY_PROXY = os.getenv("GATEWAY_PROXY_KEY", "sk-9a13a60d641a42f9a74b18d58d44a358")
BASE_URL_PROXY = "http://100.79.241.120:8045/v1"

def test_model(base_url, api_key, model_name, payload_extra=None, description=""):
    print(f"\n--- Testing {description} ---")
    print(f"URL: {base_url}")
    print(f"Model: {model_name}")
    
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": "Hãy viết một bài thơ ngắn 2 câu về AI."}
        ],
        "max_tokens": 150
    }
    if payload_extra:
        payload.update(payload_extra)
        
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/chat/completions", data=req_data)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            
            # Print response info
            reply = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            print("✅ SUCCESS!")
            print(f"Reply:\n{reply}")
            
            # Check if there is any thought/reasoning in the response
            # Some providers return it in choice.message.reasoning_content or in choice.message.content
            message = res_json.get("choices", [{}])[0].get("message", {})
            if "reasoning_content" in message:
                print(f"Thoughts (reasoning_content):\n{message['reasoning_content']}")
            elif "reasoning" in message:
                print(f"Thoughts (reasoning):\n{message['reasoning']}")
                
    except urllib.error.HTTPError as e:
        print(f"❌ FAILED (HTTP {e.code}: {e.reason})")
        try:
            err_body = e.read().decode("utf-8")
            print(f"Error Details: {err_body}")
        except Exception:
            pass
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout):
            print("❌ FAILED (Timeout)")
        else:
            print(f"❌ FAILED (Connection error: {e.reason})")
    except Exception as e:
        print(f"❌ FAILED ({e})")

if __name__ == "__main__":
    # Test case 1: Gọi qua Local AI Gateway (bây giờ đã comment out callback corrector và có drop_params: false)
    # Chúng ta truyền trực tiếp thinking_budget/thinking_level xem nó có đi qua nguyên vẹn và proxy phản hồi thế nào
    test_model(
        base_url=BASE_URL_LOCAL,
        api_key=API_KEY_LOCAL,
        model_name="gemini-3.5-flash-medium",
        payload_extra={
            "thinking_budget": 1024
        },
        description="Local AI Gateway (with thinking_budget: 1024, no corrector callback)"
    )
    
    # Test case 2: Gọi trực tiếp vào API Proxy để xem API Proxy có chấp nhận tham số thinking_budget / thinking_level không
    test_model(
        base_url=BASE_URL_PROXY,
        api_key=API_KEY_PROXY,
        model_name="gemini-3.5-flash-medium",
        payload_extra={
            "thinking_budget": 1024
        },
        description="Direct API Proxy (with thinking_budget: 1024)"
    )

    # Test case 3: Gọi trực tiếp vào API Proxy với thinking_level trong extra_body (chuẩn của Gemini API nhưng gọi dạng OpenAI proxy)
    test_model(
        base_url=BASE_URL_PROXY,
        api_key=API_KEY_PROXY,
        model_name="gemini-3.5-flash-medium",
        payload_extra={
            "extra_body": {
                "generationConfig": {
                    "thinking_config": {
                        "thinking_budget": 1024
                    }
                }
            }
        },
        description="Direct API Proxy (with nested thinking_budget in extra_body)"
    )
