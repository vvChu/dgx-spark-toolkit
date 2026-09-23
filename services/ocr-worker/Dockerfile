FROM hellohal2064/vllm-qwen3.5-gb10:blackwell-sm121

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV MODEL_CACHE_DIR=/models/datalab
ENV SURYA_DEVICE=cpu
ENV OMP_NUM_THREADS=4
ENV OPENBLAS_NUM_THREADS=4

# Install required system dependencies (libgl1, libglib for OpenCV/torchvision/PIL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /models/datalab

# Install worker requirements
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy worker application code
COPY . .

# Reset base image entrypoint (which defaults to vLLM server)
ENTRYPOINT []

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
