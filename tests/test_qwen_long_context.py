import requests
import time
import sys

BASE_URL = "http://localhost:8004/v1"
MODEL = "qwen3.5-35b"

def generate_long_text(target_tokens=15000):
    # A simple way to generate a long text is repeating a block
    # "The quick brown fox jumps over the lazy dog. " * 50 is ~218 tokens.
    # "The quick brown fox jumps over the lazy dog. " * 50 is 2250 chars.
    # Qwen tokenizer compresses very efficiently (~5.5 chars/token).
    # 40 blocks * 2250 chars = 90,000 chars -> roughly 16,000 tokens.
    chunk = "The quick brown fox jumps over the lazy dog. " * 50
    blocks_needed = 40
    
    text_blocks = []
    for i in range(blocks_needed):
        if i == blocks_needed // 2:
            text_blocks.append("\n[SECRET_KEY: DGX_SPARK_VLLM_2026]\n")
        else:
            text_blocks.append(chunk)
            
    return "".join(text_blocks)

def test_long_context():
    print("--- [3] Testing Long Context Handling (Needle in a Haystack) ---")
    print("Generating ~15K token payload...")
    haystack = generate_long_text(15000)
    
    prompt = f"Read the following long document and extract the exact SECRET_KEY.\n\n<document>\n{haystack}\n</document>\n\nWhat is the SECRET_KEY?"
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that strictly follows instructions. Output ONLY the exact SECRET_KEY without any thinking process, reasoning, or additional text."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 256,
        "temperature": 0.0
    }
    
    print("Sending payload to vLLM (this will take a while for prefill)...")
    start_time = time.time()
    try:
        response = requests.post(f"{BASE_URL}/chat/completions", json=payload, timeout=300)
        if response.status_code != 200:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return False
            
        result = response.json()
        content = result['choices'][0]['message']['content']
        total_time = time.time() - start_time
        
        usage = result.get('usage', {})
        prompt_tokens = usage.get('prompt_tokens', 0)
        
        print(f"\nResponse: {content.strip()}")
        print(f"Prompt Tokens processed: {prompt_tokens}")
        print(f"Total Time: {total_time:.2f}s")
        
        if "DGX_SPARK_VLLM_2026" in content:
            print("✅ Long Context Retrieval OK")
            return True
        else:
            print("❌ Secret Key NOT found in response.")
            return False
            
    except Exception as e:
        print(f"\n❌ Long Context Test Failed: {e}")
        return False

if __name__ == "__main__":
    test_long_context()
