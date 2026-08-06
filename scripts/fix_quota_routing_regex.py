import re

filepath = "/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml"
with open(filepath, 'r') as f:
    content = f.read()

OUT_OF_QUOTA = [
    "gemini-3-pro-high", "gemini-3-pro-low", "gemini-3.1-pro",
    "gemini-3.1-pro-high", "gemini-3.1-pro-low", "gemini-2.5-pro"
]

HAVE_QUOTA = [
    "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash-thinking",
    "gemini-3.1-flash-image", "gemini-3-pro-image"
]
# gemini-3.1-flash-lite was already handled manually by regex before, but let's make sure it's untouched or correct

def replacer(match):
    block = match.group(0)
    
    # Extract model name
    m_name = re.search(r'model_name:\s*([^\n]+)', block)
    if not m_name:
        return block
    model_name = m_name.group(1).strip()
    
    if model_name in OUT_OF_QUOTA:
        # Route to local key and real google model name
        if "3.1" in model_name or "3-pro" in model_name:
            real_model = "gemini/gemini-3.1-pro-preview"
        else:
            real_model = "gemini/gemini-1.5-pro"
            
        block = re.sub(r'model:\s*[^\n]+', f'model: {real_model}', block)
        
        # Remove api_base line if it exists
        block = re.sub(r'\n\s*api_base:[^\n]+', '', block)
        
        # Change api_key to local gemini key
        block = re.sub(r'api_key:\s*os\.environ/GATEWAY_PROXY_KEY', r'api_key: os.environ/GEMINI_API_KEY_4', block)
        
    elif model_name in HAVE_QUOTA:
        # Route to Proxy using NATIVE REST
        block = re.sub(r'model:\s*openai/(gemini-[^\n]+)', r'model: gemini/\1', block)
        block = re.sub(r'api_base:\s*os\.environ/GATEWAY_PROXY_URL', r'api_base: http://100.79.241.120:8045', block)
        
    return block

# Apply to the proxy block only (from GEMINI PRO MODELS down to GPT/OSS MODELS)
new_content = re.sub(r'  - model_name: [^\n]+\n    litellm_params:[\s\S]*?(?=\n  - model_name:|\n  # =================)', replacer, content)

with open(filepath, 'w') as f:
    f.write(new_content)

print("Safely updated litellm_config.yaml with Regex!")
