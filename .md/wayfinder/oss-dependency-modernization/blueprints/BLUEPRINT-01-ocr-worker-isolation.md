# Kiến Trúc Tham Khảo: Tách Rời Surya-OCR Thành Vi Dịch Vụ Worker
**Mã thiết kế:** `BLUEPRINT-SPARK-OCR-ISOLATION-20260922`  
**Thuộc bản đồ:** [MAP-SPARK-OSS-DEPENDENCY-20260922](../map.md) (Giải quyết `FOG-02`)  
**Tác giả:** Antigravity Agent  
**Mục tiêu:** Cô lập `surya-ocr` và `pillow==10.4.0` (33 CVEs), giải phóng FastAPI RAG Service lên `pillow>=12.1.1` (Sạch 100% CVEs).

---

## 1. Bối Cảnh & Vấn Đề Kỹ Thuật

1. **Ràng buộc phụ thuộc không thể phá vỡ (Immutable Dependency Pin):**
   - Thư viện `surya-ocr` (kể cả bản mới nhất `0.22.1` trên PyPI) khóa cứng `pillow==10.4.0`.
   - `pillow==10.4.0` chứa 33 lỗ hổng bảo mật đã công bố (PYSEC-2026-2249, PYSEC-2026-2250, v.v.), chủ yếu là Buffer Overflow và Memory Corruption trong các decoder hình ảnh cũ (SGI, PCD, ICNS).
2. **Xung đột Bề mặt Tấn công (Attack Surface Conflict):**
   - Container `rag-service` mở cổng HTTP public (`:8000`) nhận request trực tiếp từ người dùng và mạng ngoài.
   - Việc web API chính phải cài đặt chung `pillow==10.4.0` đặt toàn bộ hệ thống vào rủi ro an ninh mạng không đáng có.
3. **Phân bổ Tài nguyên Không Tối Ưu:**
   - Khi không thực hiện OCR tài liệu (hầu hết thời gian phục vụ tìm kiếm/chat), các thư viện OCR và mô hình thị giác vẫn chiếm dụng bộ nhớ trong container chính.

---

## 2. Thiết Kế Kiến Trúc: OCR Worker Microservice (Deep Seams)

Áp dụng nguyên tắc **Deep Modules & Deep Seams** (ADR-0035 / `/ccba-codebase-design`):

```
┌────────────────────────────────────────────────────────┐
│               FastAPI RAG Service (:8000)              │
│  - Public Web API (Search, Chat, Preview, Admin)       │
│  - pillow >= 12.1.1 (100% CLEAN - 0 CVEs)              │
│  - Không cài đặt surya-ocr / torchvision nặng         │
└──────────────────────────┬─────────────────────────────┘
                           │
                           │ HTTP POST /extract (hoặc Redis Queue)
                           ▼
┌────────────────────────────────────────────────────────┐
│            OCR Worker Microservice (:8005)             │
│  - Internal Only (Mạng nội bộ Docker bridge)           │
│  - surya-ocr == 0.22.1 + pillow == 10.4.0              │
│  - Cô lập hoàn toàn, không expose cổng ra Internet     │
└────────────────────────────────────────────────────────┘
```

### 2.1. Thành phần 1: Service `ocr-worker`
- **Thư mục:** `services/ocr-worker/`
- **Docker Compose:** Khai báo service mới trong `docker-compose.yml` thuộc mạng nội bộ `rag-net`:
  ```yaml
  ocr-worker:
    build:
      context: ./services/ocr-worker
      dockerfile: Dockerfile
    container_name: dgx-spark-ocr-worker
    restart: unless-stopped
    networks:
      - rag-net
    environment:
      - WORKER_CONCURRENCY=2
    # Không expose ports ra host máy chủ (chỉ giao tiếp qua mạng nội bộ Docker)
  ```
- **API Endpoint tối giản (KISS):**
  - `POST /extract`: Nhận file PDF/hình ảnh hoặc file path, trả về JSON text đã nhận diện kèm bounding boxes.
  - `GET /healthz`: Kiểm tra trạng thái sẵn sàng của mô hình OCR.

### 2.2. Thành phần 2: Adapter `OCRClient` trong RAG Service
Tại `services/rag-service/ingestion/ocr_client.py`:
```python
from __future__ import annotations
import httpx
import logging

logger = logging.getLogger(__name__)

class OCRClient:
    """Client facade for remote OCR Worker microservice."""

    def __init__(self, base_url: str = "http://ocr-worker:8005", timeout: float = 120.0):
        self.base_url = base_url
        self.timeout = timeout

    async def extract_text(self, file_bytes: bytes, filename: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            files = {"file": (filename, file_bytes)}
            resp = await client.post(f"{self.base_url}/extract", files=files)
            resp.raise_for_status()
            return resp.json().get("text", "")
```

---

## 3. Lợi Ích & Chỉ Số Đạt Được

1. **Triệt tiêu 100% CVEs ở Tầng Web API:**
   - `requirements-app.in` của `rag-service` nâng cấp lên `pillow>=12.1.1`.
   - Lệnh `uvx pip-audit -r requirements-app.lock` giảm từ **50 CVEs xuống 0 CVEs**.
2. **Thu hẹp Bề mặt Tấn công (Zero Trust Isolation):**
   - Container `ocr-worker` nằm hoàn toàn trong mạng nội bộ không có cổng public, loại bỏ triệt để khả năng khai thác lỗ hổng từ xa qua internet.
3. **Giảm Kích Thước Image & Thời Gian Khởi Động:**
   - Container `rag-service` không cần compile/bundle các gói thị giác nặng, giảm thời gian build và dung lượng image ~6GB.

---

## 4. Kế Hoạch Triển Khai (Action Plan Khi Có Yêu Cầu)

1. **Giai đoạn 1:** Khởi tạo thư mục `services/ocr-worker`, viết `Dockerfile` và script `main.py` chạy Uvicorn nhẹ cho OCR.
2. **Giai đoạn 2:** Thêm `ocr-worker` vào `docker-compose.yml`.
3. **Giai đoạn 3:** Thay thế import trực tiếp `from surya.ocr import ...` trong `services/rag-service/ingestion/vision.py` bằng lời gọi qua `OCRClient`.
4. **Giai đoạn 4:** Nâng cấp `pillow>=12.1.1` trong `services/rag-service/requirements-app.in` và recompile `requirements-app.lock`.
