import requests
import json
import time

BASE_URL = "http://localhost:8004/v1"
MODEL = "qwen3.5-35b"

TEST_CASES = [
    {
        "category": "Reasoning/Logic",
        "name": "The River Crossing Puzzle",
        "prompt": "A farmer has a wolf, a goat, and a cabbage. He needs to cross a river. His boat can only carry him and one other item. If left alone, the wolf will eat the goat, and the goat will eat the cabbage. How can he get everything across safely? Explain step-by-step.",
        "thinking": True
    },
    {
        "category": "Coding",
        "name": "Complex Python Implementation",
        "prompt": "Write a Python function to solve a Sudoku puzzle using backtracking. The input is a 9x9 grid where 0 represents empty cells. Include helper functions for validation and a clear main execution example.",
        "thinking": False
    },
    {
        "category": "Mathematics",
        "name": "Hard Counting/Logic",
        "prompt": "If you have 100 coins and 10 of them are heads up, and the rest are tails up. You are blindfolded and cannot feel which way they are facing. You must separate the coins into two piles (not necessarily equal) such that each pile has the same number of heads up coins. How do you do it?",
        "thinking": True
    },
    {
        "category": "Creative Writing/Vietnamese",
        "name": "Vietnamese Poem",
        "prompt": "Viết một bài thơ lục bát ngắn về vẻ đẹp của Vịnh Hạ Long, yêu cầu ngôn từ trau chuốt và hình ảnh gợi cảm.",
        "thinking": False
    }
]

def run_test(case):
    print(f"\n--- Testing: {case['category']} ({case['name']}) ---")
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": case["prompt"]}],
        "temperature": 0.0,
        "max_tokens": 2048,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": case["thinking"]}
    }
    
    start_time = time.time()
    try:
        response = requests.post(f"{BASE_URL}/chat/completions", json=payload, timeout=300)
        response.raise_for_status()
        end_time = time.time()
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # Check for thinking field if present (Qwen 3.5 specialized images often store thoughts in a separate field or tags)
        # For our purposes, we'll just display the main content.
        
        print(f"Time taken: {end_time - start_time:.2f}s")
        print("-" * 40)
        print(content[:1000] + ("..." if len(content) > 1000 else ""))
        print("-" * 40)
        
        return {
            "name": case["name"],
            "category": case["category"],
            "prompt": case["prompt"],
            "response": content,
            "time": end_time - start_time
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    print(f"🚀 Starting Capability Evaluation for {MODEL}")
    results = []
    for case in TEST_CASES:
        res = run_test(case)
        if res:
            results.append(res)
    
    with open("capability_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Evaluation complete. Results saved to capability_results.json")

if __name__ == "__main__":
    main()
