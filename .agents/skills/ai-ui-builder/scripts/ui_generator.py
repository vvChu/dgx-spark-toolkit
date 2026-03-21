import sys
import os
import re

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../shared'))
from vllm_client import get_image_base64, chat_completion

UI_PROMPT = """You are an expert Frontend Developer and UI/UX Designer. 
Given the provided UI mockup/design image, your task is to turn it into clean, responsive, and functional React code using Tailwind CSS for styling. 

Strict Rules for Quality:
1. Output ONLY valid React Functional Code. No markdown like ```jsx or ```tsx. Wait, just output pure text starting with `import React` or `import { ... }`.
2. Closely match the Layout, Colors, and Proportions of the image. Extract hex colors from visual elements.
3. Use modern Tailwind aesthetics: soft shadows (shadow-sm, shadow-md), rounded corners (rounded-xl, rounded-2xl), and decent padding/margins.
4. Use standard HTML elements or assume `lucide-react` for icons if you see any (e.g., `<Home className="w-5 h-5" />`).
5. Ensure the design is responsive (use grid/flex and md: lg: breakpoints where logical).
6. Do NOT include any explanations, just the raw code.
"""

COMPLEXITY_PROMPT = """Analyze the provided UI design image.
Rate its implementation complexity from 1 to 10.
- 1: Extremely simple (one button, blank page).
- 5: Average (login form, simple blog post).
- 10: Extremely complex (full dashboard, data visualization, complex grid systems).

Output ONLY a JSON object: {"complexity_score": <float>, "reasoning": "<short_string>"}
"""

def run_ui_generator(image_source, output_file="generated_ui.tsx"):
    print(f"==========================================")
    print(f"🎨 AI UI/UX BUILDER — DGX Spark Toolkit")
    print(f"==========================================\n")
    
    b64_image = get_image_base64(image_source)
    
    # Pass 1: Complexity Assessment (Fast Model)
    print("[*] Assessing UI complexity...")
    complexity_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": COMPLEXITY_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}
                }
            ]
        }
    ]
    
    try:
        raw_eval = chat_completion(complexity_messages, model="gemini-3-flash", temperature=0.0)
        eval_data = json.loads(re.sub(r'^```json\n|```$', '', raw_eval.strip(), flags=re.MULTILINE).strip())
        score = float(eval_data.get("complexity_score", 5))
        reasoning = eval_data.get("reasoning", "No reasoning provided.")
    except Exception as e:
        print(f"Warning: Complexity assessment failed ({e}). Defaulting to score 5.")
        score = 5.0
        reasoning = "Fallback due to eval error."

    # Routing Decision
    if score > 8.5:
        target_model = "smartest-brain" # Claude Opus 4.6 Thinking
        model_label = "Claude Opus Thinking (Ultimate Quality - Thinker)"
    elif score > 5.0:
        target_model = "smart-brain" # Claude 3.5 Sonnet
        model_label = "Claude 3.5 Sonnet (Premium Quality)"
    else:
        target_model = "rag-core" # Local Qwen
        model_label = "rag-core (Local - High Speed)"

    print(f"📊 Complexity Score: {score}/10")
    print(f"💬 Reason: {reasoning}")
    print(f"🧠 Routing to: {model_label}\n")
    
    # Pass 2: Code Generation
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
    
    print(f"[*] Generating React/Tailwind code... Please wait...\n")
    
    try:
        raw_code = chat_completion(
            messages, 
            temperature=0.0, 
            max_tokens=4000, 
            model=target_model
        )
        
        # Clean up any markdown blocks
        clean_code = re.sub(r'^```[a-zA-Z]*\n|```$', '', raw_code.strip(), flags=re.MULTILINE).strip()
        
        with open(output_file, 'w') as f:
            f.write(clean_code)
            
        print(f"✅ Success! Source Code saved to: {output_file}")
            
    except Exception as e:
        print(f"\n[-] API Error via Gateway: {e}")
        
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ui_generator.py <image_path_or_url> [output_file.tsx]")
        sys.exit(1)
        
    img_src = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else "generated_ui.tsx"
    run_ui_generator(img_src, out_file)
