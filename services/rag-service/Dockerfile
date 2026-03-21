# Use Blackwell-optimized image as base
FROM hellohal2064/vllm-qwen3.5-gb10:blackwell-sm121

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    python3-dev \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install application dependencies
COPY requirements.txt .
# Filter out torch from requirements as it's already in the base image (vLLM version)
RUN grep -v "torch" requirements.txt > requirements_no_torch.txt && \
    pip3 install --no-cache-dir -r requirements_no_torch.txt

# Copy application code
COPY . .

# Non-root user — rag-service uses CPU-only reranker/embedding, no CUDA perms needed
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Reset entrypoint from base image
ENTRYPOINT []

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=30s --retries=10 --start-period=120s \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
