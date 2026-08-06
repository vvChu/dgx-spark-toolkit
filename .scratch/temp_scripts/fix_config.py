import sys
file_path = "/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml"
with open(file_path, "r") as f:
    content = f.read()

content = content.replace("openai/gemma-3-27b-it", "openai/gemma-4-31b-it")
content = content.replace("openai/gemma-3-12b-it", "openai/gemma-4-26b-a4b-it")
content = content.replace("openai/gemma-3-4b-it", "openai/gemma-4-26b-a4b-it")

with open(file_path, "w") as f:
    f.write(content)

print("Replaced model names successfully.")
