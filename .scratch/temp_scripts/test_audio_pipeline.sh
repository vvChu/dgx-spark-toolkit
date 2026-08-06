#!/bin/bash
set -e

# Restart AI Gateway
echo "Restarting AI Gateway..."
docker compose restart ai-gateway

echo "Waiting 10s for AI Gateway to initialize..."
sleep 10

# Extract Master Key if possible
export $(grep '^LITELLM_MASTER_KEY=' .env | xargs)

# Create a dummy silent wav file
python3 -c "
import wave, struct
with wave.open('test_audio.wav', 'w') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(struct.pack('<h', 0) * 16000)
"

echo "=== First Request (Should hit Whisper model) ==="
time curl -s -X POST http://localhost:8090/v1/audio/transcriptions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -F "file=@test_audio.wav" \
  -F "model=audio-primary"

echo -e "\n\n=== Second Request (Should hit Redis Cache) ==="
time curl -s -X POST http://localhost:8090/v1/audio/transcriptions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -F "file=@test_audio.wav" \
  -F "model=audio-primary"
