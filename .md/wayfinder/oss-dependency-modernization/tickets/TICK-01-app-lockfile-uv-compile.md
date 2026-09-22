# Ticket [TICK-01]: Tạo File Ràng buộc App & Biên dịch Lockfile Bằng UV Trừ Hardware Packages

**Bản đồ cha:** [Bản đồ Định hướng Hiện đại hóa Dependency](../map.md)  
**Phân loại:** `Task [AFK]`  
**Trạng thái:** `Completed (Done)`  
**Assignee:** Antigravity Agent  
**Ngày hoàn tất:** 22/09/2026  
**Phụ thuộc:** Không có (Unblocked)  

---

## 1. Mục tiêu đã hoàn thành
Thiết lập file input ràng buộc cho tầng ứng dụng [requirements-app.in](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/requirements-app.in) và sử dụng engine `uv` để biên dịch ra [requirements-app.lock](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/requirements-app.lock) tất định 100%, bảo vệ tuyệt đối kernel CUDA 13.0 và PyTorch dev của phần cứng NVIDIA DGX Spark GB10.

## 2. Chi tiết Triển khai đã áp dụng
1. Đã tạo `services/rag-service/requirements-app.in`:
   - Phân tách rõ ràng Tier A (tiện ích, web, nlp) và Tier B (database clients khóa trần khớp với server containers: `pymilvus<2.7.0`, `neo4j<5.27.0`, `redis<6.0.0`).
   - Không khai báo `torch`, `torchvision`, `vllm`.
2. Đã biên dịch thành công qua lệnh trừ package phần cứng:
   ```bash
   uv pip compile services/rag-service/requirements-app.in \
     --no-emit-package torch \
     --no-emit-package torchvision \
     --no-emit-package torchaudio \
     --no-emit-package triton \
     --no-emit-package vllm \
     --no-emit-package flashinfer-python \
     --no-emit-package cuda-toolkit \
     --no-emit-package nvidia-cublas \
     --no-emit-package nvidia-cuda-cupti \
     --no-emit-package nvidia-cuda-nvrtc \
     --no-emit-package nvidia-cuda-runtime \
     --no-emit-package nvidia-cudnn-cu13 \
     --no-emit-package nvidia-cufft \
     --no-emit-package nvidia-cufile \
     --no-emit-package nvidia-curand \
     --no-emit-package nvidia-cusolver \
     --no-emit-package nvidia-cusparse \
     --no-emit-package nvidia-cusparselt-cu13 \
     --no-emit-package nvidia-nccl-cu13 \
     --no-emit-package nvidia-nvjitlink \
     --no-emit-package nvidia-nvshmem-cu13 \
     --no-emit-package nvidia-nvtx \
     --output-file services/rag-service/requirements-app.lock
   ```
3. Đã cập nhật [services/rag-service/Dockerfile](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/Dockerfile):
   - Loại bỏ hoàn toàn thủ thuật `grep -v "torch"` không tất định cũ.
   - Thay thế bằng:
     ```dockerfile
     # Install application dependencies via deterministic lockfile
     COPY requirements-app.lock requirements.txt ./
     RUN pip3 install --no-cache-dir --no-deps -r requirements-app.lock
     ```

## 3. Nghiệm thu Thực tế
- [x] File `requirements-app.lock` được sinh thành công trong 22ms, phân giải chính xác 139 packages.
- [x] Lệnh kiểm tra `grep -E "(^torch==|^torchvision==|^nvidia-|^vllm==)" services/rag-service/requirements-app.lock` trả về `CLEAN`.
- [x] Lệnh kiểm thử cài đặt dry-run `uv pip install --dry-run --no-deps -r requirements-app.lock` thành công 100%.
