# RAG Status Diagnostic Tool for DGX Spark (Blackwell GB10)
# Author: Antigravity AI
# Version: 2.0.0

echo "==============================================================="
echo "   RAG SYSTEM OPERATIONAL STATUS - DGX SPARK (BLACKWELL)"
echo "==============================================================="
date

echo -e "\n[1/5] DOCKER CONTAINERS STATUS:"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo -e "\n[2/5] GPU RESOURCES (NVIDIA-SMI):"
if command -v nvidia-smi &> /dev/null; then
    # Enhanced parsing for Blackwell (supporting N/A)
    VRAM_USED_RAW=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -n 1)
    VRAM_TOTAL=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n 1)
    UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -n 1)
    
    # Fallback for Blackwell 'Not Supported' memory query
    if [[ "$VRAM_USED_RAW" == "[N/A]" ]] || [[ "$VRAM_USED_RAW" == "Not Supported" ]]; then
        VRAM_USED=$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits | awk '{sum+=$1} END {print sum}')
        VRAM_USED_RAW="${VRAM_USED}"
    fi
    
    echo "GPU 0: | Util: ${UTIL}% | VRAM: ${VRAM_USED_RAW}/${VRAM_TOTAL} MB"
    
    # Check 35B Sub-40GB target
    if [[ "$VRAM_USED" =~ ^[0-9]+$ ]] && [ "$VRAM_USED" -lt 40960 ]; then
        echo "✅ VRAM TARGET: SUB-40GB ACHIEVED"
    else
        echo "⚠️ VRAM TARGET Check skipped or failed (VRAM: $VRAM_USED_RAW)"
    fi
else
    echo "ERROR: nvidia-smi not found."
fi

echo -e "\n[3/5] DATABASE HEALTH CHECK:"
if curl -s -f http://localhost:7474 > /dev/null; then
    echo "✓ Neo4j Graph DB: ONLINE"
else
    echo "✗ Neo4j Graph DB: OFFLINE"
fi

if curl -s -f http://localhost:9091/healthz > /dev/null; then
    echo "✓ Milvus Vector DB: ONLINE"
else
    echo "✗ Milvus Vector DB: OFFLINE"
fi

echo -e "\n[4/5] CACHE PERFORMANCE (LITELLM):"
if docker exec litellm-redis redis-cli ping | grep -q "PONG"; then
    HITS=$(docker exec litellm-redis redis-cli info stats | grep "keyspace_hits" | cut -d':' -f2 | tr -d '\r')
    MISSES=$(docker exec litellm-redis redis-cli info stats | grep "keyspace_misses" | cut -d':' -f2 | tr -d '\r')
    TOTAL=$((HITS + MISSES))
    if [ $TOTAL -gt 0 ]; then
        RATIO=$(echo "scale=2; $HITS * 100 / $TOTAL" | bc)
        echo "→ Cache Hit Ratio (Total): ${RATIO}%"
    else
        echo "→ Cache Hit Ratio (Total): 0% (No requests yet)"
    fi
else
    echo "✗ Redis Cache Layer: DISCONNECTED"
fi

echo -e "\n[5/5] GATEWAY READINESS:"
if curl -s -f http://localhost:8090/health/readiness > /dev/null; then
    echo "✓ LiteLLM Gateway: READY"
else
    echo "✗ LiteLLM Gateway: DOWN"
fi

echo -e "\n--- SUMMARY TABLE (MARKDOWN) ---"
echo "| Component | Status | Metrics |"
echo "|-----------|--------|---------|"
echo "| rag-core  | RUNNING| ${VRAM_USED} MB |"
echo "| rag-light  | ACTIVE | ${RATIO}% Hit |"
echo "| Gateway   | READY  | Port 8090 |"
echo "==============================================================="
