import asyncio
import httpx
import json
import time
import statistics
from typing import List, Dict, Any

API_BASE = "http://localhost:8005"
TIMEOUT = 120.0

GOLD_DATASET = [
    {
        "category": "Technical Regulation (Stainless Steel)",
        "query": "Thép không gỉ là gì và hàm lượng Crom tối thiểu là bao nhiêu theo QCVN 20:2019/BKHCN?",
        "language": "vi"
    },
    {
        "category": "Telecomm Norms (Surveying)",
        "query": "Định mức khảo sát để lập dự toán công trình bưu chính viễn thông được quy định tại văn bản nào?",
        "language": "vi"
    },
    {
        "category": "Guard Law (VN)",
        "query": "Đối tượng cảnh vệ bao gồm những ai theo quy định của Luật Cảnh vệ 2017?",
        "language": "vi"
    },
    {
        "category": "Land Management (Phu Tho)",
        "query": "Quy định về quản lý và sử dụng đất trên địa bàn tỉnh Phú Thọ theo Quyết định 16/UBND năm 2024?",
        "language": "vi"
    },
    {
        "category": "Cross-Language (Steel)",
        "query": "What are the management requirements for imported stainless steel in Vietnam?",
        "language": "en"
    }
]

async def run_benchmark():
    print("🚀 Starting Comprehensive RAG Benchmark...")
    print("==========================================")
    
    results = []
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for item in GOLD_DATASET:
            print(f"\n[Testing] Category: {item['category']}")
            print(f"Query: {item['query']}")
            
            start_time = time.time()
            try:
                # 1. Call Chat API
                chat_resp = await client.post(
                    f"{API_BASE}/chat",
                    json={"query": item["query"], "language": item["language"]}
                )
                chat_resp.raise_for_status()
                chat_data = chat_resp.json()
                latency = time.time() - start_time
                
                answer = chat_data["answer"]
                context = [c["text"] for c in chat_data.get("context", [])]
                
                # 2. Call Evaluation API
                eval_resp = await client.post(
                    f"{API_BASE}/evaluate",
                    json={
                        "query": item["query"],
                        "answer": answer,
                        "context": context
                    }
                )
                eval_resp.raise_for_status()
                eval_data = eval_resp.json()
                
                res = {
                    "category": item["category"],
                    "query": item["query"],
                    "latency": round(latency, 2),
                    "faithfulness": eval_data.get("faithfulness", 0.0),
                    "relevancy": eval_data.get("relevancy", 0.0),
                    "cached": chat_data.get("cached", False)
                }
                results.append(res)
                
                print(f"  ✅ Done. Latency: {res['latency']}s | Faith: {res['faithfulness']} | Rel: {res['relevancy']} | Cached: {res['cached']}")
                
            except Exception as e:
                print(f"  ❌ Failed: {e}")
                results.append({
                    "category": item["category"],
                    "query": item["query"],
                    "error": str(e)
                })

    print("\n\n==========================================")
    print("📊 Benchmark Summary")
    print("==========================================")
    
    valid_results = [r for r in results if "error" not in r]
    if valid_results:
        avg_faith = statistics.mean([r["faithfulness"] for r in valid_results])
        avg_rel = statistics.mean([r["relevancy"] for r in valid_results])
        avg_lat = statistics.mean([r["latency"] for r in valid_results])
        
        print(f"Total Tests: {len(results)}")
        print(f"Success Rate: {len(valid_results)/len(results)*100:.1f}%")
        print(f"Average Faithfulness: {avg_faith:.2f}")
        print(f"Average Relevancy: {avg_rel:.2f}")
        print(f"Average Latency: {avg_lat:.2f}s")
        
        # Breakdown by category
        print("\nCategory Breakdown:")
        for r in results:
            status = "✅" if "error" not in r else "❌"
            score = (r['faithfulness'] + r['relevancy']) / 2 if "error" not in r else 0
            print(f"  {status} {r['category']:20}: Score {score:.2f} | Latency {r.get('latency', 'N/A')}s")
    else:
        print("No valid results collected.")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
