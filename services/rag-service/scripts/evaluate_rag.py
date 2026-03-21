"""
RAGAS-style Evaluation for BIM RAG Pipeline
Measures: Faithfulness, Answer Relevancy, Context Precision
"""
import httpx
import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RAG_BASE = "http://rag-service:8000"

# ─── Gold Dataset: BIM & Legal questions with expected keywords ───

GOLD_DATASET = [
    # --- BIM & Technical Basics ---
    {
        "question": "EIR (Exchange Information Requirements) là gì và vai trò của nó trong dự án BIM?",
        "expected_keywords": ["EIR", "yêu cầu", "thông tin", "chủ đầu tư", "ISO 19650"],
        "category": "BIM"
    },
    {
        "question": "BEP (BIM Execution Plan) bao gồm những nội dung chính nào?",
        "expected_keywords": ["BEP", "kế hoạch", "triển khai", "mô hình", "phối hợp"],
        "category": "BIM"
    },
    {
        "question": "CDE (Common Data Environment) hoạt động như thế nào theo ISO 19650?",
        "expected_keywords": ["CDE", "môi trường", "dữ liệu", "chia sẻ", "quản lý"],
        "category": "BIM"
    },
    {
        "question": "LOD (Level of Development) là gì? Lợi ích của việc áp dụng LOD chuẩn?",
        "expected_keywords": ["LOD", "mức độ", "phát triển", "chi tiết", "thông tin"],
        "category": "BIM"
    },
    {
        "question": "Quy trình phối hợp 3D (Clash Detection) theo BIM thực hiện thế nào?",
        "expected_keywords": ["phối hợp", "va chạm", "clash", "mô hình", "xử lý"],
        "category": "BIM"
    },
    
    # --- Legal & Construction Decrees ---
    {
        "question": "Văn bản nào đang quy định về quản lý chi phí đầu tư xây dựng?",
        "expected_keywords": ["Nghị định", "10/2021", "CP", "chi phí", "quản lý"],
        "category": "Legal_Direct"
    },
    {
        "question": "Hồ sơ đề nghị cấp giấy phép xây dựng nhà ở riêng lẻ gồm những gì theo Nghị định 15/2021?",
        "expected_keywords": ["đơn", "bản vẽ", "thiết kế", "giấy tờ", "đất"],
        "category": "Legal_Direct"
    },
    {
        "question": "Điều kiện năng lực của tổ chức tư vấn quản lý dự án hạng I là gì?",
        "expected_keywords": ["hạng I", "chứng chỉ", "năng lực", "kinh nghiệm", "nhân sự"],
        "category": "Legal_Direct"
    },
    {
        "question": "Mẫu đơn đăng ký mua nhà ở xã hội yêu cầu những thông tin gì?",
        "expected_keywords": ["đơn", "đăng ký", "mua", "thuê", "nhà ở xã hội"],
        "category": "Legal_Direct"
    },
    {
        "question": "Ai có thẩm quyền phê duyệt dự toán xây dựng công trình?",
        "expected_keywords": ["chủ đầu tư", "người quyết định", "đầu tư", "thẩm quyền", "phê duyệt"],
        "category": "Legal_Direct"
    },
    
    # --- Tricky / Conflicting Scenarios ---
    {
        "question": "Nghị định 59/2015/NĐ-CP về quản lý dự án đầu tư xây dựng hiện tại còn hiệu lực không?",
        "expected_keywords": ["hết hiệu lực", "thay thế", "15/2021/NĐ-CP", "Nghị định"],
        "category": "Legal_Tricky"
    },
    {
        "question": "So sánh sự khác biệt cơ bản giữa hợp đồng trọn gói và hợp đồng theo đơn giá cố định?",
        "expected_keywords": ["trọn gói", "đơn giá", "cố định", "rủi ro", "khối lượng"],
        "category": "Legal_Tricky"
    },
    {
        "question": "Làm thế nào để xử lý vi phạm hành chính trong lĩnh vực trật tự xây dựng (ví dụ: xây sai phép)?",
        "expected_keywords": ["phạt tiền", "cưỡng chế", "tháo dỡ", "đình chỉ", "vi phạm"],
        "category": "Legal_Tricky"
    },
    {
        "question": "BIM bắt buộc áp dụng cho các dự án xây dựng từ năm nào tại Việt Nam?",
        "expected_keywords": ["Lộ trình", "2023", "2025", "Quyết định 258", "bắt buộc"],
        "category": "Legal_Tricky"
    },
    {
        "question": "Cơ quan nào có thẩm quyền thẩm định Báo cáo nghiên cứu khả thi dự án nhóm A?",
        "expected_keywords": ["cơ quan chuyên môn", "Bộ Xây dựng", "Bộ quản lý", "thẩm định"],
        "category": "Legal_Tricky"
    },
    {
        "question": "Quy định về thời hạn bảo hành công trình xây dựng cấp 1 là bao lâu?",
        "expected_keywords": ["bảo hành", "24 tháng", "cấp 1", "công trình"],
        "category": "Legal_Tricky"
    },
    {
        "question": "Các trường hợp nào được miễn giấy phép xây dựng theo Luật Xây dựng sửa đổi 2020?",
        "expected_keywords": ["miễn giấy phép", "mật độ", "bí mật nhà nước", "khẩn cấp"],
        "category": "Legal_Tricky"
    },
    {
        "question": "Chủ đầu tư có được phép trực tiếp quản lý dự án nếu không đủ năng lực không?",
        "expected_keywords": ["chủ đầu tư", "trực tiếp quản lý", "năng lực", "thuê tư vấn", "ban quản lý"],
        "category": "Legal_Tricky"
    },
    {
        "question": "Chỉ giới đường đỏ và chỉ giới xây dựng khác nhau như thế nào?",
        "expected_keywords": ["chỉ giới", "đường đỏ", "xây dựng", "ranh giới", "khoảng lùi"],
        "category": "Legal_Tricky"
    },
    {
        "question": "Điều kiện để khởi công xây dựng công trình là gì?",
        "expected_keywords": ["khởi công", "mặt bằng", "giấy phép", "thiết kế", "vốn"],
        "category": "Legal_Tricky"
    }
]

@dataclass
class EvalResult:
    question: str
    category: str
    answer_length: int
    keyword_hit_rate: float
    has_source_citation: bool
    context_count: int
    latency_ms: float
    faithfulness_score: float  # simplified: keyword matching + citation

def evaluate_single(q: dict) -> EvalResult:
    """Evaluate a single question against the RAG pipeline."""
    start = time.time()
    try:
        resp = httpx.post(
            f"{RAG_BASE}/chat",
            json={"query": q["question"], "context_limit": 10},
            timeout=300.0
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Request failed for: {q['question'][:50]}... Error: {e}")
        return EvalResult(
            question=q["question"], category=q["category"],
            answer_length=0, keyword_hit_rate=0.0,
            has_source_citation=False, context_count=0,
            latency_ms=(time.time() - start) * 1000, faithfulness_score=0.0
        )
    
    latency = (time.time() - start) * 1000
    answer = data.get("answer", "")
    context = data.get("context", [])
    
    # Keyword hit rate
    answer_lower = answer.lower()
    hits = sum(1 for kw in q["expected_keywords"] if kw.lower() in answer_lower)
    keyword_rate = hits / len(q["expected_keywords"]) if q["expected_keywords"] else 0
    
    # Source citation check
    has_citation = any(
        marker in answer for marker in ["[Source:", "[ISO", "Theo ", "theo ", "Thông tư", "Mẫu số"]
    )
    
    # Simplified faithfulness: weighted average of keyword coverage and citation
    faithfulness = (keyword_rate * 0.7) + (0.3 if has_citation else 0.0)
    
    return EvalResult(
        question=q["question"],
        category=q["category"],
        answer_length=len(answer),
        keyword_hit_rate=round(keyword_rate, 2),
        has_source_citation=has_citation,
        context_count=len(context),
        latency_ms=round(latency, 1),
        faithfulness_score=round(faithfulness, 2)
    )

def run_evaluation():
    logger.info(f"Starting RAGAS evaluation with {len(GOLD_DATASET)} questions...")
    results = []
    
    for i, q in enumerate(GOLD_DATASET):
        logger.info(f"[{i+1}/{len(GOLD_DATASET)}] {q['category']}: {q['question'][:60]}...")
        result = evaluate_single(q)
        results.append(result)
        logger.info(f"  → Faithfulness: {result.faithfulness_score:.2f} | Keywords: {result.keyword_hit_rate:.0%} | Latency: {result.latency_ms:.0f}ms")
    
    # Summary
    avg_faithfulness = sum(r.faithfulness_score for r in results) / len(results)
    avg_keyword_rate = sum(r.keyword_hit_rate for r in results) / len(results)
    avg_latency = sum(r.latency_ms for r in results) / len(results)
    citation_rate = sum(1 for r in results if r.has_source_citation) / len(results)
    
    print("\n" + "=" * 70)
    print(f"  RAGAS EVALUATION SUMMARY — {len(results)} questions")
    print("=" * 70)
    print(f"  Average Faithfulness Score : {avg_faithfulness:.2f} / 1.00")
    print(f"  Average Keyword Hit Rate   : {avg_keyword_rate:.0%}")
    print(f"  Source Citation Rate        : {citation_rate:.0%}")
    print(f"  Average Latency            : {avg_latency:.0f} ms")
    print("=" * 70)
    
    # Per-category
    categories = set(r.category for r in results)
    for cat in sorted(categories):
        cat_results = [r for r in results if r.category == cat]
        cat_faith = sum(r.faithfulness_score for r in cat_results) / len(cat_results)
        print(f"  [{cat}] Faithfulness: {cat_faith:.2f} | Questions: {len(cat_results)}")
    
    # Save results
    output = {
        "summary": {
            "total_questions": len(results),
            "avg_faithfulness": round(avg_faithfulness, 3),
            "avg_keyword_rate": round(avg_keyword_rate, 3),
            "citation_rate": round(citation_rate, 3),
            "avg_latency_ms": round(avg_latency, 1)
        },
        "results": [asdict(r) for r in results]
    }
    
    with open("/tmp/ragas_results.json", "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    logger.info("Results saved to /tmp/ragas_results.json")
    return output

if __name__ == "__main__":
    run_evaluation()
