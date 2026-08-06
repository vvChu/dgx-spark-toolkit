# =============================================================================
# whisper-local: speaches + ctranslate2 CUDA (aarch64 / Blackwell GB10)
# =============================================================================
# WHY THIS EXISTS:
#   The official ghcr.io/speaches-ai/speaches:latest-cuda image is built on
#   x86_64 runners using QEMU for ARM64. QEMU cannot compile CUDA kernels,
#   so the ctranslate2 wheel inside the image is CPU-only (no CUDA support).
#
#   This Dockerfile builds ctranslate2 from source natively on the DGX Spark
#   (aarch64 + NVIDIA GB10 Blackwell, sm_120) to get real GPU inference.
#
# BUILD TIME: ~15-25 min (first time). Subsequent builds use Docker layer cache.
# =============================================================================

# Stage 1: Build ctranslate2 with CUDA support for aarch64
# Use CUDA 12.6 devel image (Ubuntu 24.04 compatible, closest stable to host CUDA 13.0)
# Note: Host driver 580.142 supports CUDA 13.0, but nvcr.io/nvidia/cuda:13.x images
# are not yet widely available. CUDA 12.6 containers run fine on CUDA 13.0 host
# via backward-compatibility guarantee.
ARG CUDA_IMAGE=nvcr.io/nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04
FROM ${CUDA_IMAGE} AS ctranslate2-builder

LABEL maintainer="dgx-spark-toolkit"
LABEL description="ctranslate2 CUDA build stage for aarch64 Blackwell (sm_120)"

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ninja-build \
    git \
    python3-dev \
    python3-pip \
    python3-venv \
    pybind11-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Python build deps
RUN pip3 install --no-cache-dir --break-system-packages \
    pybind11 \
    setuptools \
    wheel

# Clone CTranslate2 at a pinned stable tag (compatible with faster-whisper)
# faster-whisper 1.x requires ctranslate2 >= 4.0
ARG CT2_VERSION=v4.5.0
RUN git clone --recursive --branch ${CT2_VERSION} \
    https://github.com/OpenNMT/CTranslate2.git /opt/ctranslate2

WORKDIR /opt/ctranslate2

# Build with CUDA + cuDNN for Blackwell (sm_120)
# sm_120 = NVIDIA GB10 Blackwell (DGX Spark)
# Also include sm_90 (Hopper H100) for broader compatibility
# CUDAARCHS env forces nvcc to compile for both sm_90 (Hopper) and sm_120 (Blackwell GB10)
# CMAKE_CUDA_ARCHITECTURES is the modern cmake way; CUDA_ARCH_LIST is the legacy FindCUDA way.
# We use both to ensure compatibility regardless of which cmake module picks it up.
ENV CUDAARCHS="120"
RUN echo "Force rebuild for sm_120 CMake fix" && mkdir build && cd build && cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DWITH_CUDA=ON \
    -DWITH_CUDNN=ON \
    -DWITH_MKL=OFF \
    -DOPENMP_RUNTIME=NONE \
    -DCMAKE_CUDA_ARCHITECTURES="120" \
    -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda \
    -G Ninja \
    && ninja -j$(nproc) \
    && ninja install \
    && ldconfig

# Build Python wheel
RUN cd python && pip3 install --break-system-packages pybind11 \
    && python3 setup.py bdist_wheel --dist-dir /opt/ct2-wheels

# =============================================================================
# Stage 2: Final speaches image with custom ctranslate2 wheel installed
# =============================================================================
FROM ghcr.io/speaches-ai/speaches:latest-cuda AS final

LABEL org.opencontainers.image.description="speaches with native CUDA ctranslate2 for aarch64 Blackwell (GB10)"

USER root

# speaches uses uv venv at /home/ubuntu/speaches/.venv — no global pip3
# Install the CUDA-compiled ctranslate2 wheel into the venv, overriding CPU-only wheel
# Copy compiled libctranslate2.so from builder (lives in /usr/local/lib after ninja install)
COPY --from=ctranslate2-builder /usr/local/lib/libctranslate2.so* /usr/local/lib/
# Copy Python wheel
COPY --from=ctranslate2-builder /opt/ct2-wheels/*.whl /tmp/
RUN VIRTUAL_ENV=/home/ubuntu/speaches/.venv /bin/uv pip install --no-cache-dir /tmp/ctranslate2*.whl \
    && rm /tmp/ctranslate2*.whl

# Register all CUDA/ctranslate2 lib paths
RUN find /home/ubuntu/speaches/.venv -maxdepth 7 -path "*/nvidia/*/lib" -type d \
    > /etc/ld.so.conf.d/venv-nvidia.conf \
    && echo "/usr/local/lib" >> /etc/ld.so.conf.d/venv-nvidia.conf \
    && ldconfig

# Patch STT Router to forcefully enable vad_filter if batched_mode is True
# This auto-corrects requests from strict clients (like OpenAI SDK) that drop custom parameters
RUN sed -i 's/vad_filter=vad_filter,/vad_filter=True if config.whisper.use_batched_mode else vad_filter,/g' /home/ubuntu/speaches/src/speaches/routers/stt.py

USER ubuntu

# NOTE: Cannot verify CUDA at build time (no GPU during docker build).
# Verification runs automatically at container startup via speaches health check.
# To verify manually after deploying:
#   docker exec whisper-local /home/ubuntu/speaches/.venv/bin/python -c \
#     "import ctranslate2; print(ctranslate2.get_supported_compute_types('cuda'))"

ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=8000
EXPOSE 8000
CMD ["uvicorn", "--factory", "speaches.main:create_app"]
