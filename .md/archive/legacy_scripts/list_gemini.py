import requests
import os

API_KEY = os.environ.get("GEMINI_API_KEY_3") or os.environ.get("GEMINI_API_KEY", "")
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
response = requests.get(url)
models = response.json().get('models', [])
for m in models:
    if 'gemini' in m['name']:
        print(m['name'])
