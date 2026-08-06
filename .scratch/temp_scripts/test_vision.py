import requests
import json
import base64

url = "http://localhost:8090/v1/chat/completions"

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer sk-spark-secure-key-2026"
}

# A simple 1x1 red pixel PNG in base64
base64_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

payload = {
    "model": "qwen-local-primary",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What is the primary color of this image? Please answer very briefly."
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    }
                }
            ]
        }
    ],
    "max_tokens": 150
}

print("Sending request to AI Gateway...")
try:
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    print("Status Code:", response.status_code)
    try:
        print("Response JSON:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        print("Raw response:", response.text)
except Exception as e:
    print(f"Error: {e}")
