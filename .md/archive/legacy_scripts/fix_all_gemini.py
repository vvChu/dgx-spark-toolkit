import re

filepath = "/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml"
with open(filepath, 'r') as f:
    content = f.read()

# Replace openai/gemini-* with gemini/gemini-*
content = re.sub(r'model: openai/(gemini-[^\n]+)', r'model: gemini/\1', content)

# For gemini/ models, if api_base is GATEWAY_PROXY_URL, change it to http://100.79.241.120:8045
# We can do this by finding blocks with model: gemini/ and replacing api_base: os.environ/GATEWAY_PROXY_URL
def replacer(match):
    block = match.group(0)
    if 'model: gemini/' in block:
        block = block.replace('api_base: os.environ/GATEWAY_PROXY_URL', 'api_base: http://100.79.241.120:8045')
    return block

content = re.sub(r'  - model_name: [^\n]+\n    litellm_params:[\s\S]*?(?=\n  - model_name:|\n  # =================)', replacer, content)

with open(filepath, 'w') as f:
    f.write(content)

print("Updated litellm_config.yaml successfully!")
