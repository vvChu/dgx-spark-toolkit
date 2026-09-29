# Design Record: Kiến Trúc Chốt Chặn Xác Thực Trích Dẫn Pháp Lý 3 Tầng (Citation Noul Verifier)

> **Tham chiếu chính thức:** [docs/adr/0006-three-tier-citation-noul-verifier.md](../../../docs/adr/0006-three-tier-citation-noul-verifier.md)  
> **Ticket:** [TICK-03](../wayfinder/system-one-decision-architecture/tickets/TICK-03-noul-citation-verifier-design.md)  
> **Bản đồ:** [MAP-SPARK-SYSTEM-ONE-20260929](../wayfinder/system-one-decision-architecture/map.md)  

Tài liệu này ghi nhận quyết định kiến trúc cốt lõi của **TICK-03**:
- Bác bỏ việc dùng `bge-reranker-v2-m3` cho bài toán xác thực trích dẫn (tránh lỗi relevance $\ne$ entailment).
- Xây dựng hệ thống 3 Tầng: Tầng 0 (Định danh Regex) $\to$ Tầng 1 (Tách mệnh đề) $\to$ Tầng 2 (Mô hình NLI Đa ngữ 3 nhãn).
- Phân định rõ chính sách 3 trạng thái: `Verified`, `Contradiction` (gỡ và cảnh báo), và `Unverified` (giữ kèm cờ để kỹ sư kiểm tra).
- Quy chuẩn hóa tập gán nhãn 600 mẫu có hard negatives theo quy định của FOG-01.
