# ccba:allow-raw-model-file
import urllib.request, json, os

key = os.popen("grep '^LITELLM_MASTER_KEY' .env | cut -d '=' -f 2").read().strip()
base_url = "http://localhost:8090"

models = [
    {
        "model_name": "whisper-primary",
        "litellm_params": {
            "model": "openai/whisper-1",
            "api_base": "http://whisper-local:8000/v1",
            "api_key": "unused",
            "timeout": 1800
        },
        "model_info": {
            "mode": "audio_transcription"
        }
    },
    {
        "model_name": "whisper-local",
        "litellm_params": {
            "model": "openai/whisper-1",
            "api_base": "http://whisper-local:8000/v1",
            "api_key": "unused",
            "timeout": 1800
        },
        "model_info": {
            "mode": "audio_transcription"
        }
    }
]

for model in models:
    req = urllib.request.Request(
        f"{base_url}/model/new",
        data=json.dumps(model).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Added {model['model_name']}:", response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Failed {model['model_name']}:", e.code, e.read().decode())
