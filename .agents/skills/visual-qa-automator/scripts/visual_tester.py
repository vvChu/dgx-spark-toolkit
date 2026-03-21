import sys
import os

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../shared'))
from vllm_client import get_image_base64, chat_completion, VLLM_MODEL

QA_PROMPT = """You are a highly detailed and strict Visual Quality Assurance (QA) Automation Engineer.
I am providing you with two images:
1. The original design mockup (Image 1 - The Ground Truth).
2. The actual coded UI screenshot (Image 2 - The Built UI).

Your task is to carefully compare Image 2 against Image 1 and write a Visual Testing Report.
Please include:
1. A Similarity Score (out of 100%).
2. Detailed list of visual discrepancies (e.g., incorrect padding, wrong font weight, mismatched colors, misaligned buttons, missing elements). Be extremely specific.
3. Suggestions on how to fix the CSS/Tailwind classes in the coded UI to match the design.

Write the report in Vietnamese.
"""

def run_visual_tester(design_img, coded_img):
    print(f"==========================================")
    print(f"🕵️  VISUAL QA AUTOMATOR RUNNING")
    print(f"🧠 Model: {VLLM_MODEL} (vLLM)")
    print(f"📸 Image 1 (Design): {design_img}")
    print(f"📸 Image 2 (Coded): {coded_img}")
    print(f"==========================================\n")
    
    b64_img1 = get_image_base64(design_img)
    b64_img2 = get_image_base64(coded_img)
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": QA_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_img1}"}
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_img2}"}
                }
            ]
        }
    ]
    
    print("[*] Analyzing discrepancies between the two images...\n")
    
    try:
        report = chat_completion(messages, temperature=0.2, max_tokens=2048)
        
        print("✍️ BÁO CÁO KIỂM THỬ:")
        print("------------------------------------------")
        print(report)
        print("------------------------------------------")
        print("\n✅ Hoàn thành phân tích Visual QA!")
            
    except Exception as e:
        print(f"\n[-] API Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Cú pháp: python visual_tester.py <anh_thiet_ke.png> <anh_code_thuc_te.png>")
        sys.exit(1)
        
    design_path = sys.argv[1]
    coded_path = sys.argv[2]
    
    run_visual_tester(design_path, coded_path)
