# Bản đồ Định hướng (Wayfinding Map): Hiện đại hóa Quản lý Dependency & Khóa Phiên Bản OSS
**Mã bản đồ:** `MAP-SPARK-OSS-DEPENDENCY-20260922`  
**Trạng thái:** `Completed (100% Tickets Closed)`  
**Hệ thống liên quan:** Backend (`services/rag-service`), Frontend (`services/frontend`), CI/CD (`.github/workflows/ci.yml`), Server Containers (`docker-compose.yml`)  
**Hạ tầng mục tiêu:** NVIDIA DGX Spark (Grace Blackwell GB10, aarch64, CUDA 13.0, 128GB Unified Memory)  

---

## 1. Điểm đích (Destination)
Thiết lập một hệ thống quản lý, kiểm tra định kỳ và cập nhật các gói mã nguồn mở (OSS) đạt chuẩn **Tất định (Deterministic) — An toàn phần cứng (Blackwell-Safe) — Kiểm thử siêu tốc (Fast CI) — Kiến trúc bền vững (Deep Seams)**:
1. **Khóa phiên bản tất định (Deterministic Lockfile)**: 100% các package tầng ứng dụng được quản lý qua `requirements-app.in` và khóa phiên bản bằng `requirements-app.lock` (sử dụng engine `uv pip compile`), hoàn toàn loại trừ (không đụng chạm/ghi đè) kernel CUDA 13.0, PyTorch dev và vLLM pre-baked của phần cứng Blackwell GB10.
2. **Tối ưu hóa CI Suite (Shift-Left Fast Gate)**: Tách triệt để GPU/Heavy AI packages ra khỏi CI runner x86_64, hoàn thiện cơ chế Stubbing tại [conftest.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/tests/conftest.py), giảm thời gian cài đặt CI từ 2m45s xuống $\le 15$ giây mà vẫn đảm bảo 100% (408/408) tests chạy pass.
3. **Bịt kín các vết rò rỉ kiến trúc (Seal Leaky Seams)**: 100% cuộc gọi Milvus và Neo4j trong [pipeline.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py) được bọc kín sau [MilvusRepository](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/repositories/milvus_repo.py) và [Neo4jRepository](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/repositories/neo4j_repo.py). Thu hồi raw driver export để bảo vệ triệt để nguyên lý Locality.
4. **Cơ chế Kiểm tra Định kỳ & An ninh (Safe Auditing & Outdated Workflows)**: Cung cấp script chuẩn hóa `check_dependency_updates.sh` cho lập trình viên và tích hợp bước kiểm tra phòng vệ (`pip-audit`, `npm audit --omit=dev --audit-level=critical`) vào CI workflow mà không gây false-alarm chặn build.

---

## 2. Ghi chú (Notes)
- **Hạ tầng máy chủ**: NVIDIA DGX Spark (Grace Blackwell GB10, aarch64, CUDA 13.0, Driver 580.178.04, 128GB Unified Memory).
- **Ràng buộc phần cứng**: Base container `hellohal2064/vllm-qwen3.5-gb10:blackwell-sm121` chứa sẵn `torch==2.12.0.dev20260301+cu130` compile nội bộ (không có trên PyPI). Tuyệt đối không dùng cờ `--index-url` kéo PyTorch từ PyPI ghi đè vào container.
- **Quy chuẩn kiến trúc**: Tuân thủ nghiêm ngặt chuẩn mực Deep Modules & Deep Seams theo [ccba-codebase-design](file:///home/vvc/Codebase/dgx-spark-toolkit/.agents/skills/ccba-codebase-design/SKILL.md) và ADR-0035.
- **Kỹ năng áp dụng**: `/ccba-wayfinder`, `/ccba-codebase-design`, `/boost` (Adversarial Review).

---

## 3. Quyết định đã chốt (Decisions so far)
- [x] **[DEC-01] Bảo tồn Nguyên trạng Kernel Blackwell qua `--no-emit-package`**: Không cố gắng map `torch` vào lockfile PyPI; sử dụng cờ `--no-emit-package` của `uv` để phân giải dependencies ứng dụng mà không ghi bất kỳ package phần cứng nào vào lockfile.
- [x] **[DEC-02] Phân tầng Quản trị 3 Tiers (Tier A/B/C)**: 
  - *Tier A (Dev/Utilities)*: Cập nhật linh hoạt minor/patch khi CI pass.
  - *Tier B (DB Clients)*: Khóa trần (upper bound) khớp chặt chẽ với container daemon trong `docker-compose.yml` (Milvus 2.6.x, Neo4j 5.26.x).
  - *Tier C (Hardware AI)*: Khóa cứng bất biến, chỉ nâng cấp khi có đánh giá bench-testing tương thích SM121.
- [x] **[DEC-03] Kiểm tra An ninh Phòng thủ (Defensive Auditing)**: Loại bỏ `npm audit fix --force` trên Frontend để bảo vệ đồ thị tri thức `react-force-graph`; cấu hình CI chỉ quét production dependencies (`--omit=dev --audit-level=critical`).
- [x] **[DEC-04] Chuẩn hóa Công cụ `uv`**: Tận dụng engine `/home/vvc/.local/bin/uv` có sẵn trên DGX Spark cho toàn bộ tác vụ compile và audit backend.
- [x] **[DEC-05] Chuẩn hóa Lockfile Ứng dụng & Dockerfile**: Đã tạo [requirements-app.in](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/requirements-app.in) và biên dịch [requirements-app.lock](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/requirements-app.lock) sạch 100% không chứa package CUDA/PyTorch; cập nhật [Dockerfile](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/Dockerfile) cài đặt qua `pip3 install --no-deps` thay cho `grep -v torch` hack.
- [x] **[DEC-06] Stub Hermetic cho CI Runner & Tinh gọn requirements-ci**: Bổ sung stub `sentence_transformers` và `FlagEmbedding` vào [conftest.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/tests/conftest.py), loại bỏ ~800MB torch/models khỏi [requirements-ci.txt](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/requirements-ci.txt), và biên dịch [requirements-ci.lock](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/requirements-ci.lock). 405 unit tests pass 100% trong 2.03s.
- [x] **[DEC-07] Bịt kín Leaky Seams & Thu hồi Raw Driver**: Đã xóa bỏ 100% direct SDK imports của `pymilvus` và `neo4j` khỏi [pipeline.py](file:///home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/ingestion/pipeline.py); chuyển toàn bộ khởi tạo schema/collection vào `MilvusRepository` và `Neo4jRepository`; đóng gói quản lý vòng đời trong `DocumentStore`; xóa bỏ `@property def driver` khỏi `Neo4jRepository` để bảo vệ nguyên lý Locality.
- [x] **[DEC-08] Xây dựng Script Kiểm tra Tự động & Tích hợp Security Audit CI**: Hoàn thiện `scripts/check_dependency_updates.sh` hỗ trợ kiểm tra outdated theo 3 Tiers, tích hợp `pip-audit` và `npm audit --omit=dev --audit-level=critical`. Bổ sung job `security-audit` vào `.github/workflows/ci.yml`.

---

## 4. Danh sách Ticket & Biên giới (Frontier Tickets)

| Mã Ticket | Tên Ticket | Phân loại | Trạng thái | Assignee |
| :--- | :--- | :---: | :---: | :---: |
| **[TICK-01](tickets/TICK-01-app-lockfile-uv-compile.md)** | [Tạo File Ràng buộc App & Biên dịch Lockfile Bằng UV Trừ Hardware Packages](tickets/TICK-01-app-lockfile-uv-compile.md) | `Task [AFK]` | **Completed** | Antigravity Agent |
| **[TICK-02](tickets/TICK-02-ci-conftest-stub-speedup.md)** | [Hoàn thiện Stub Conftest & Tối ưu Tốc độ CI Runner](tickets/TICK-02-ci-conftest-stub-speedup.md) | `Task [AFK]` | **Completed** | Antigravity Agent |
| **[TICK-03](tickets/TICK-03-seal-pipeline-leaky-seams.md)** | [Refactor Pipeline Ingestion Bịt kín Leaky Seams Milvus & Neo4j](tickets/TICK-03-seal-pipeline-leaky-seams.md) | `Task [AFK]` | **Completed** | Antigravity Agent |
| **[TICK-04](tickets/TICK-04-automated-audit-check-script.md)** | [Xây dựng Script Tự Động Kiểm Tra Cập Nhật & Tích hợp CI Audit](tickets/TICK-04-automated-audit-check-script.md) | `Task [AFK]` | **Completed** | Antigravity Agent |

---

## 5. Sương mù chiến trận / Chưa xác định rõ (Not yet specified)
- **FOG-01 (Kế hoạch Nâng cấp Milvus 3.0 & Neo4j 6.x)**: Server container `milvusdb/milvus:v2.6.14` đang ổn định. Khi có nhu cầu nâng lên 3.0.x (cải tiến sparse index), sẽ cần ticket nghiên cứu quy trình sao lưu metadata trên `etcd`/MinIO và migrate dữ liệu.
- **FOG-02 (Kế hoạch Đưa Reranker/Embedding lên GPU Blackwell)**: Hiện tại container RAG đang chạy CPU mode (`FORCE_CPU_RERANKER=1`) để dành trọn VRAM cho `vllm-35b`. Khi VRAM scheduler hỗ trợ dynamic paging, sẽ đánh giá lại việc offload sang GPU.
- **FOG-03 (Internal Mirroring cho Base Docker Image)**: Image `hellohal2064/vllm-qwen3.5-gb10:blackwell-sm121` đang kéo từ Docker Hub công cộng. Cần kế hoạch sao lưu bản image này về private registry nội bộ để phòng ngừa rủi ro tài khoản bị xóa.

---

## 6. Ngoài phạm vi (Out of scope)
- **Tự động merge PR (Dependabot auto-merge)**: Đã bị bác bỏ trong đợt phản biện do nguy cơ làm gãy tương thích phần cứng Blackwell GB10.
- **Thay đổi phiên bản Database Server trong Docker Compose**: Giữ nguyên `neo4j:5.26.25` và `milvus:v2.6.14` trong đợt này nhằm bảo toàn tính toàn vẹn của dữ liệu pháp lý hiện tại.
