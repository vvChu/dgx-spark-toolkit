import requests
import json
import time

BASE_URL = "http://localhost:8004/v1"
MODEL = "qwen3.5-35b"

def test_streaming():
    print("--- [1] Testing Streaming Response ---")
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Write a short fun story about a robot learning to cook pho (max 100 words)."}],
        "stream": True,
        "max_tokens": 512,
        "temperature": 0.5
    }
    
    start_time = time.time()
    try:
        response = requests.post(f"{BASE_URL}/chat/completions", json=payload, stream=True, timeout=300)
        response.raise_for_status()
        
        first_token_time = None
        print("Response: ", end="", flush=True)
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: ") and decoded_line != "data: [DONE]":
                    data = json.loads(decoded_line[6:])
                    if 'choices' in data and len(data['choices']) > 0:
                        delta = data['choices'][0].get('delta', {})
                        if 'content' in delta:
                            if first_token_time is None:
                                first_token_time = time.time()
                            print(delta['content'], end="", flush=True)
        print("\n")
        
        total_time = time.time() - start_time
        ttft = first_token_time - start_time if first_token_time else 0
        print(f"✅ Streaming OK | TTFT: {ttft:.2f}s | Total Time: {total_time:.2f}s")
        return True
    except Exception as e:
        print(f"\n❌ Streaming Failed: {e}")
        return False

def test_json_mode():
    print("\n--- [2] Testing JSON Mode (Structured Output) ---")
    schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "person_info",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                    "profession": {"type": "string"},
                    "skills": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["name", "age", "profession", "skills"]
            }
        }
    }
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Extract the information into valid JSON based on the user's input."},
            {"role": "user", "content": "Alice is a 29 year old data scientist who is an expert in Python, SQL, and Machine Learning."}
        ],
        "response_format": schema,
        "max_tokens": 256,
        "temperature": 0.1
    }
    
    start_time = time.time()
    try:
        response = requests.post(f"{BASE_URL}/chat/completions", json=payload, timeout=300)
        response.raise_for_status()
        result = response.json()
        
        content = result['choices'][0]['message']['content']
        parsed_json = json.loads(content)
        
        print("Generated JSON:")
        print(json.dumps(parsed_json, indent=2))
        
        # Simple validation
        assert "Alice" in parsed_json.get("name", "")
        assert parsed_json.get("age") == 29
        assert "data scientist" in parsed_json.get("profession", "").lower()
        assert len(parsed_json.get("skills", [])) >= 3
        
        print(f"✅ JSON Mode OK | Elapsed: {time.time() - start_time:.2f}s")
        return True
    except AssertionError:
        print(f"\n❌ JSON Schema Validation Failed. Raw output: {content}")
        return False
    except Exception as e:
        print(f"\n❌ JSON Mode Failed: {e}")
        return False

if __name__ == "__main__":
    test_streaming()
    test_json_mode()
