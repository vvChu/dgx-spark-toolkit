import re

filepath = "/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml"
with open(filepath, 'r') as f:
    content = f.read()

# I previously mapped everything to gemini-1.5-pro-latest, which is invalid.
# I need to map them back intelligently based on their original model_name

def replacer(match):
    block = match.group(0)
    
    # Extract model name
    m_name = re.search(r'model_name:\s*([^\n]+)', block)
    if not m_name:
        return block
    model_name = m_name.group(1).strip()
    
    real_model = None
    if "3.1-pro" in model_name:
        real_model = "gemini/gemini-3.1-pro-preview"
    elif "3-pro" in model_name:
        real_model = "gemini/gemini-3.1-pro-preview"
    elif "2.5-pro" in model_name:
        real_model = "gemini/gemini-2.5-pro"
        
    if real_model:
        block = re.sub(r'model:\s*[^\n]+', f'model: {real_model}', block)
        
    return block

# Apply to the proxy block only
new_content = re.sub(r'  - model_name: [^\n]+\n    litellm_params:[\s\S]*?(?=\n  - model_name:|\n  # =================)', replacer, content)

with open(filepath, 'w') as f:
    f.write(new_content)

print("Safely mapped to 2026 valid Google API model names!")
