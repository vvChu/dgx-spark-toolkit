#!/bin/bash
# Setup Remote Access for DGX Spark AI Services
# Exposes vLLM endpoints and Docker Compose services to the network
# Usage: sudo ./setup-remote-access.sh

set -e

if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root (sudo)"
  exit 1
fi

echo "🔧 Configuring DGX Spark for remote access..."
echo "=============================================="

# --- 1. Configure UFW firewall rules ---
echo ""
echo "📡 Opening required ports..."

declare -A PORTS=(
  [8004]="vLLM Qwen 3.5 35B"
  [8003]="vLLM Qwen 3.5 4B (Fallback)"
  [8000]="RAG Service (Internal)"
  [8090]="AI Gateway (LiteLLM)"
  [9090]="Prometheus"
  [3000]="Grafana"
  [5173]="RAG Frontend"
  [8005]="RAG Service (Production)"
)

for port in "${!PORTS[@]}"; do
  ufw allow "$port/tcp" comment "${PORTS[$port]}" 2>/dev/null && \
    echo "  ✅ Port $port — ${PORTS[$port]}" || \
    echo "  ℹ️  Port $port — already open or ufw not active"
done

# --- 2. Verify Docker containers are bound to 0.0.0.0 ---
echo ""
echo "🐳 Checking Docker port bindings..."
docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null | while read line; do
  echo "  $line"
done

# --- 3. Get IP addresses for remote access ---
echo ""
echo "🌐 Available network interfaces:"
TAILSCALE_IP=$(ip -4 addr show tailscale0 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "")
if [ -n "$TAILSCALE_IP" ]; then
  echo "  🚀 Tailscale IP (Recommended): $TAILSCALE_IP"
fi

ip -4 addr show | grep -oP 'inet \K[\d.]+' | grep -v '127.0.0.1' | while read ip; do
  if [ "$ip" != "$TAILSCALE_IP" ]; then
    echo "  • $ip"
  fi
done

# --- 4. Print connection info ---
MAIN_IP=${TAILSCALE_IP:-$(ip -4 route get 1 | awk '{print $7; exit}')}
echo ""
echo "=============================================="
echo "✅ Remote access configured!"
echo ""
echo "Connect from other machines using:"
echo "  • 🏠 RAG Portal:  http://$MAIN_IP:5173"
echo "  • 🤖 vLLM 35B:    http://$MAIN_IP:8004/v1
  • 🤖 vLLM 4B:     http://$MAIN_IP:8003/v1
  • 🔌 AI Gateway:  http://$MAIN_IP:8090
"
echo "  • 📊 Grafana:     http://$MAIN_IP:3000"
echo ""
echo "💡 Tip: If http://$MAIN_IP:5173 is unreachable, ensure"
echo "   you are connected to Tailscale or check port forwarding."
echo "=============================================="
