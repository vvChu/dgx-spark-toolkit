# Data Quality Awareness & RAG Health Monitor

## 1. Ảnh hưởng của Deadlock (Treo hệ thống) đến Chất lượng Dữ liệu
Khi vLLM hoặc hệ thống bị deadlock liên tục, các vấn đề sau sẽ xảy ra:

*   **Dữ liệu rác/trùng lặp (Duplicate Data)**: Nếu hệ thống nạp dữ liệu vào Milvus thành công nhưng lại bị treo trước khi cập nhật trạng thái "Hoàn thành" vào Neo4j, lần chạy sau hệ thống sẽ nạp lại file đó, dẫn đến trùng lặp dữ liệu trong Vector DB.
*   **Thiếu hụt liên kết (Broken Graph)**: Một số file có thể đã được đánh chỉ mục vector nhưng chưa kịp tạo các mối quan hệ `REPLACES` hay `AMENDS` trong Neo4j, làm giảm độ chính xác của tìm kiếm Multi-hop.
*   **Dữ liệu "mồ côi" (Orphaned Files)**: File bị kẹt ở trạng thái `PROCESSING` trong 1 giờ (theo logic default), khiến dữ liệu mới nhất không được cập nhật kịp thời.

## 2. Giải pháp Kiểm soát Chất lượng (Data Quality Assurance)

Để đảm bảo dữ liệu nạp vào RAG đúng yêu cầu thiết kế, chúng tôi đề xuất 3 tầng kiểm soát:

### Tầng 1: Tính Giao dịch (Transactional Ingestion)
*   **Cleanup before Retry**: Khi bắt đầu xử lý một file, nếu phát hiện nó đã bị lỗi trước đó hoặc đang Processing (quá lâu), hệ thống sẽ thực hiện xóa bỏ các Chunk cũ trong Milvus của file đó trước khi nạp lại.
*   **Two-Phase Commit (Logic)**: Chỉ đánh dấu `DONE` trong Neo4j sau khi đã kiểm tra số lượng chunk trong Milvus khớp với số trang của file.

### Tầng 2: Công cụ Hậu kiểm (Post-ingestion Audit)
Tôi sẽ cung cấp một script `audit_data_health.py` để:
*   Đếm số lượng file thực tế trong Folder Source.
*   Đối chiếu với số lượng Node `Document` trong Neo4j.
*   Kiểm tra số lượng Chunk trong Milvus.
*   Phát hiện các file "Empty" (có Node nhưng không có Vector).

### Tầng 3: Xác thực trực quan (Visual Grounding)
*   Sử dụng tọa độ BBox (v7) để hiển thị trực tiếp vùng văn bản được trích xuất trên PDF gốc, giúp User kiểm tra xem OCR có chính xác không.

## 3. Bản kế hoạch triển khai công cụ Audit
Tôi sẽ tạo một công cụ script trực tiếp trong service RAG để anh có thể chạy bất cứ lúc nào.
