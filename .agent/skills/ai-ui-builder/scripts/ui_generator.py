import sys
import os
import re

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../shared'))
from vllm_client import get_image_base64, chat_completion, VLLM_MODEL

UI_PROMPT = """You are an expert Frontend Developer. 
Given the provided UI mockup/design image, your task is to turn it into clean, responsive, and functional React code using Tailwind CSS for styling. 

Rules:
1. Output ONLY valid React Functional Component code.
2. DO NOT include markdown code blocks ```jsx ... ``` or ```tsx ... ```. Just purely return the source code plain text. Let the very first character be `import React` or `<div`.
3. Closely match the Layout, Colors, and Typography of the provided image.
4. Extract color themes (like background colors, button colors) directly from the visual elements in the design and use inline hex or tailwind equivalent.
"""

def run_ui_generator(image_source, output_file="generated_ui.tsx"):
    print(f"==========================================")
    print(f"🎨 AI UI/UX BUILDER RUNNING")
    print(f"🧠 Model: {VLLM_MODEL} (vLLM)")
    print(f"==========================================\n")
    
    b64_image = get_image_base64(image_source)
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": UI_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}
                }
            ]
        }
    ]
    
    print("[*] Giving image to Qwen3.5 (vLLM) and rendering code... This may take a minute...\n")
    
    try:
        raw_code = chat_completion(messages, temperature=0.1, max_tokens=2048)
        
        # Clean up any markdown blocks if the AI stubbornly adds them
        clean_code = re.sub(r'^```[a-z]*\n|```$', '', raw_code.strip(), flags=re.MULTILINE).strip()
        
        with open(output_file, 'w') as f:
            f.write(clean_code)
            
        print(f"✅ Success! React/Tailwind Source Code saved to: {output_file}")
            
    except Exception as e:
        print(f"\n[-] API Error: {e}")
        
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ui_generator.py <image_path_or_url> [output_file.tsx]")
        sys.exit(1)
        
    img_src = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else "generated_ui.tsx"
    run_ui_generator(img_src, out_file)
