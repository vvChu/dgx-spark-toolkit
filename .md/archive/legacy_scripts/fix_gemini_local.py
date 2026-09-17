import re

filepath = "/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml"
with open(filepath, 'r') as f:
    content = f.read()

# For all gemini models in the proxy section (lines 120 to 220), we replace api_base and api_key
def replacer(match):
    block = match.group(0)
    if 'model: gemini/' in block:
        # Remove api_base line
        block = re.sub(r'\n\s*api_base: http://100\.79\.241\.120:8045', '', block)
        # Change api_key to local gemini key
        block = re.sub(r'api_key: os\.environ/GATEWAY_PROXY_KEY', r'api_key: os.environ/GEMINI_API_KEY_3', block)
    return block

# Apply to the proxy block only
new_content = re.sub(r'  - model_name: [^\n]+\n    litellm_params:[\s\S]*?(?=\n  - model_name:|\n  # =================)', replacer, content)

with open(filepath, 'w') as f:
    f.write(new_content)

print("Fixed all Gemini models to use local Google API keys directly!")
