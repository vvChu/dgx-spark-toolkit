import re

filepath = "/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml"
with open(filepath, 'r') as f:
    content = f.read()

# Revert gemini models back to proxy EXCEPT gemini-3.1-flash-lite
def replacer(match):
    block = match.group(0)
    # Don't revert gemini-3.1-flash-lite because we KNOW it works directly and breaks on proxy
    if 'model_name: gemini-3.1-flash-lite' in block:
        return block
    if 'model: gemini/' in block:
        block = re.sub(r'model: gemini/(gemini-[^\n]+)', r'model: openai/\1', block)
        block = re.sub(r'\n\s*api_key: os\.environ/GEMINI_API_KEY_3', r'\n      api_base: os.environ/GATEWAY_PROXY_URL\n      api_key: os.environ/GATEWAY_PROXY_KEY', block)
    return block

# Apply to the proxy block only
new_content = re.sub(r'  - model_name: [^\n]+\n    litellm_params:[\s\S]*?(?=\n  - model_name:|\n  # =================)', replacer, content)

with open(filepath, 'w') as f:
    f.write(new_content)

print("Reverted all other Gemini models to proxy!")
