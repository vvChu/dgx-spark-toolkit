import site
import os

packages = site.getsitepackages()
for p in packages:
    registry_path = os.path.join(p, "vllm/model_executor/models/registry.py")
    if os.path.exists(registry_path):
        with open(registry_path, "r") as f:
            content = f.read()

        if "Qwen3_5MoeForConditionalGeneration" not in content:
            new_content = content.replace(
                '"Qwen3MoeForCausalLM": ("qwen3_moe", "Qwen3MoeForCausalLM")',
                '"Qwen3MoeForCausalLM": ("qwen3_moe", "Qwen3MoeForCausalLM"),\n    "Qwen3_5MoeForConditionalGeneration": ("qwen3_moe", "Qwen3MoeForCausalLM")'
            )
            with open(registry_path, "w") as f:
                f.write(new_content)
            print("Successfully patched vllm model registry on v0.15.1!")
            break
        else:
            print("Already patched.")
            break
