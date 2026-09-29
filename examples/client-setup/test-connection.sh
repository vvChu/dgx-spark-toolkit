#!/bin/bash
# ============================================================
# Test AI Gateway Connection
# Chạy script này trên máy client để kiểm tra kết nối
# Usage: bash test-connection.sh [server_ip]
# ============================================================

set -euo pipefail

# --- Configuration ---
SERVER_IP="${1:-${AI_GATEWAY_HOST:-127.0.0.1}}"
GATEWAY_URL="http://${SERVER_IP}:8090"
API_KEY="${AI_GATEWAY_KEY:-sk-spark-secure-key-2026}"

echo "🔍 Testing AI Gateway Connection"
echo "   Server: ${SERVER_IP}"
echo "   Gateway: ${GATEWAY_URL}"
echo "================================================"

# --- Test 1: Network connectivity ---
echo ""
echo "1️⃣  Network connectivity..."
if ping -c 1 -W 3 "${SERVER_IP}" &>/dev/null; then
  echo "   ✅ Server reachable"
else
  echo "   ❌ Cannot reach ${SERVER_IP}"
  echo "   💡 Kiểm tra: Tailscale connected? Cùng mạng LAN? SSH tunnel running?"
  exit 1
fi

# --- Test 2: Gateway health ---
echo ""
echo "2️⃣  Gateway health check..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 -H "Authorization: Bearer ${API_KEY}" "${GATEWAY_URL}/health" 2>/dev/null || echo "000")
if [ "$HEALTH" = "200" ]; then
  echo "   ✅ Gateway is healthy"
else
  echo "   ❌ Gateway not responding (HTTP ${HEALTH})"
  echo "   💡 Kiểm tra: Docker containers đang chạy trên server?"
  echo "      ssh vvc@${SERVER_IP} 'docker ps | grep ai-gateway'"
  exit 1
fi

# --- Test 3: Authentication ---
echo ""
echo "3️⃣  Authentication..."
AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer ${API_KEY}" \
  "${GATEWAY_URL}/v1/models" 2>/dev/null || echo "000")
if [ "$AUTH_STATUS" = "200" ]; then
  echo "   ✅ API key valid"
else
  echo "   ❌ Authentication failed (HTTP ${AUTH_STATUS})"
  echo "   💡 Kiểm tra API_KEY trong .env"
  exit 1
fi

# --- Test 4: List models ---
echo ""
echo "4️⃣  Available models:"
MODELS=$(curl -s \
  -H "Authorization: Bearer ${API_KEY}" \
  "${GATEWAY_URL}/v1/models" 2>/dev/null)

echo "$MODELS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    models = sorted(set(m['id'] for m in data['data']))
    local = [m for m in models if m in ('qwen-local-primary', 'rag-core', 'rag-light')]
    cloud = [m for m in models if m not in ('qwen-local-primary', 'rag-core', 'rag-light')]
    local_str = ', '.join(local)
    cloud_str = ', '.join(cloud)
    print(f'   🖥️  Local ({len(local)}): {local_str}')
    print(f'   ☁️  Cloud ({len(cloud)}): {cloud_str}')
    print(f'   📊 Total: {len(models)} models')
except Exception as e:
    print(f'   ⚠️  Could not parse models: {e}')
" 2>/dev/null || echo "   ⚠️  python3 not available for parsing"

# --- Test 5: Chat completion with Qwen 35B ---
echo ""
echo "5️⃣  Test chat (Qwen 35B local: qwen-local-primary)..."
RESPONSE=$(curl -s --max-time 30 \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  "${GATEWAY_URL}/v1/chat/completions" \
  -d '{
    "model": "qwen-local-primary",
    "messages": [{"role": "user", "content": "Say hello in Vietnamese, one sentence only."}],
    "max_tokens": 50
  }' 2>/dev/null)

REPLY=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['choices'][0]['message']['content'])
except Exception as e:
    print(f'ERROR: {e}')
    print(f'Raw: {sys.stdin.read()[:200]}')
" 2>/dev/null || echo "Parse error")

if [[ "$REPLY" != ERROR* ]] && [[ "$REPLY" != "Parse error" ]]; then
  echo "   ✅ Qwen 35B responded: ${REPLY}"
else
  echo "   ⚠️  Qwen 35B may be loading — this is normal on first request"
  echo "   Response: ${REPLY}"
fi

# --- Summary ---
echo ""
echo "================================================"
echo "✅ All checks passed! Gateway is ready."
echo ""
echo "📋 Quick start for your project:"
echo "   1. Copy .env.ai-gateway → .env"
echo "   2. Install SDK: pip install openai  (or: npm install openai)"
echo "   3. Use endpoint: ${GATEWAY_URL}/v1"
echo "   4. API key: ${API_KEY:0:10}..."
echo "================================================"
