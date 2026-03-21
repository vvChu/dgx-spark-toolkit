import sys
import os
import json

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../shared'))
from vllm_client import get_image_base64, chat_completion, VLLM_MODEL

JSON_PROMPT = """You are a meticulous Data Extraction API. 
Your ONLY job is to extract the requested information from the provided image and return it exclusively as a valid JSON object.
Do NOT include any greetings, markdown formatting (like ```json), explanations, or extra text.
If a requested field is missing from the image, set its value to null.

User Request: {user_request}
"""

def extract_data(image_path, user_request):
    print(f"==========================================")
    print(f"📄 MULTIMODAL OCR & EXTRACTOR")
    print(f"🧠 Model: {VLLM_MODEL} (vLLM)")
    print(f"==========================================\n")
    
    b64_img = get_image_base64(image_path)
    final_prompt = JSON_PROMPT.format(user_request=user_request)
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": final_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                }
            ]
        }
    ]
    
    print("[*] Processing document with vLLM... Please wait...\n")
    
    try:
        raw_output = chat_completion(messages, temperature=0.0, max_tokens=1024)
        
        print("💡 KẾT QUẢ TRÍCH XUẤT (JSON):")
        print("------------------------------------------")
        
        try:
            parsed_json = json.loads(raw_output)
            print(json.dumps(parsed_json, indent=4, ensure_ascii=False))
        except json.JSONDecodeError:
            print("Warning: Output could not be parsed as strictly valid JSON.")
            print(raw_output)
            
        print("------------------------------------------")

    except Exception as e:
        print(f"\n[-] API Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cú pháp: python data_extractor.py <duong_dan_tai_lieu_anh> [\"yeu_cau_trich_xuat\"]")
        sys.exit(1)
        
    img_path = sys.argv[1]
    request_str = sys.argv[2] if len(sys.argv) > 2 else "Extract all possible key-value data pairs you can find."
    
    extract_data(img_path, request_str)
