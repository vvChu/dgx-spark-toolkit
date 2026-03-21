import requests
import json
import time
import sys

def test_complex_timeline():
    # Note: Use 8005 as mapped in docker-compose
    url = "http://localhost:8005/search" 
    query = "Điều 123 Luật Xây dựng hiện hành sau tất cả các sửa đổi là gì? Bản vẽ BIM số DWG-2023-A1 của dự án ABC có còn hiệu lực theo luật mới không?"
    
    print(f"--- Sending Query: {query} ---")
    start = time.time()
    try:
        response = requests.post(
            url,
            json={"query": query, "limit": 5},
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        print(f"ERROR calling API: {e}")
        sys.exit(1)
        
    latency = time.time() - start
    
    print("\n=== SEARCH RESULTS (Hybrid + Graph Timeline) ===")
    found_timeline = False
    for i, res in enumerate(result.get("results", [])):
        print(f"\n[{i+1}] Source: {res.get('source')} | Status: {res.get('status')}")
        if "legal_timeline_summary" in res:
            found_timeline = True
            print(f"TIMELINE SUMMARY: {res['legal_timeline_summary'][:200]}...")
        else:
            print("No timeline summary available for this hit.")
            
    print(f"\nTotal latency: {latency:.2f}s")
    
    if found_timeline:
        print("✅ PASSED: GraphRAG Timeline Traversal verified.")
    else:
        print("⚠️ WARNING: No timelines were generated for top hits. Check if documents have relations in Neo4j.")

if __name__ == "__main__":
    test_complex_timeline()
