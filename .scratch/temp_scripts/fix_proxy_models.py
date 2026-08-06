import sys
file_path = "/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml"
with open(file_path, "r") as f:
    content = f.read()

# Fix gemini-3-pro models
content = content.replace("model: openai/gemini-3-pro-high", "model: openai/gemini-3.1-pro-high")
content = content.replace("model: openai/gemini-3-pro-low", "model: openai/gemini-3.1-pro-low")

# Fix gemini-3.1-pro missing model ID (proxy only has -high and -low)
# We will map gemini-3.1-pro to gemini-3.1-pro-low as a safe default
content = content.replace("model: openai/gemini-3.1-pro\n", "model: openai/gemini-3.1-pro-low\n")

with open(file_path, "w") as f:
    f.write(content)

print("Fixed API Proxy model names successfully.")
