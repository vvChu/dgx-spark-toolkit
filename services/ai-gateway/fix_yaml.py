import yaml

with open('/home/vvc/Codebase/dgx-spark-toolkit/services/ai-gateway/litellm_config.yaml', 'r') as f:
    orig_lines = f.readlines()

out = []

out.append("""x-templates:
  ocr-tier4-base: &ocr-tier4-base
    model: gemini/gemini-3-flash
    rpm: 5
    tpm: 250000
    timeout: 120

  ocr-fallback-base: &ocr-fallback-base
    model: gemini/gemini-2.5-flash-preview
    rpm: 5
    tpm: 250000
    timeout: 120

  ocr-primary-base: &ocr-primary-base
    model: gemini/gemini-3.1-flash-lite
    rpm: 15
    tpm: 250000
    timeout: 120

  text-gemma-base: &text-gemma-base
    model: openai/gemma-4-31b-it
    api_base: https://generativelanguage.googleapis.com/v1beta/openai/
    rpm: 30
    tpm: 15000

  text-gemma-12b-base: &text-gemma-12b-base
    model: openai/gemma-4-26b-a4b-it
    api_base: https://generativelanguage.googleapis.com/v1beta/openai/
    rpm: 30
    tpm: 15000

  reasoning-gemma-base: &reasoning-gemma-base
    model: openai/gemma-4-31b-it
    api_base: https://generativelanguage.googleapis.com/v1beta/openai/
    rpm: 15
    tpm: 250000

  reasoning-fallback-base: &reasoning-fallback-base
    model: openai/gemma-4-26b-it
    api_base: https://generativelanguage.googleapis.com/v1beta/openai/
    rpm: 15
    tpm: 250000

""")

for i in range(231):
    out.append(orig_lines[i])

def add_keys(model_name, base_anchor, start_key=2, end_key=11):
    for k in range(start_key, end_key + 1):
        out.append(f"  - model_name: {model_name}\n")
        out.append(f"    litellm_params:\n")
        out.append(f"      <<: *{base_anchor}\n")
        out.append(f"      api_key: os.environ/GEMINI_API_KEY_{k}\n")

out.append("  # ── ocr-tier4: gemini-3-flash ──\n")
add_keys("ocr-tier4", "ocr-tier4-base")

out.append("\n  # ── ocr-fallback: gemini-2.5-flash-preview (acting as fallback) ──\n")
add_keys("ocr-fallback", "ocr-fallback-base")

out.append("\n  # ── ocr-primary: gemini-3.1-flash-lite ──\n")
add_keys("ocr-primary", "ocr-primary-base")

out.append("\n  # ── text-gemma ──\n")
add_keys("text-gemma", "text-gemma-base")

out.append("\n  # ── text-gemma-12b ──\n")
add_keys("text-gemma-12b", "text-gemma-12b-base")

out.append("\n  # ── text-gemma-4b ──\n")
add_keys("text-gemma-4b", "text-gemma-12b-base")

out.append("\n  # ── reasoning-gemma & reasoning-fallback ──\n")
for k in range(2, 12):
    out.append(f"  - model_name: reasoning-gemma\n")
    out.append(f"    litellm_params:\n")
    out.append(f"      <<: *reasoning-gemma-base\n")
    out.append(f"      api_key: os.environ/GEMINI_API_KEY_{k}\n")
    out.append(f"  - model_name: reasoning-fallback\n")
    out.append(f"    litellm_params:\n")
    out.append(f"      <<: *reasoning-fallback-base\n")
    out.append(f"      api_key: os.environ/GEMINI_API_KEY_{k}\n")

# Find router_settings in orig
router_start = 0
for i, line in enumerate(orig_lines):
    if line.startswith('router_settings:'):
        router_start = i
        break

router_end = len(orig_lines)
router_block = orig_lines[router_start:router_end]

new_router_block = []
for line in router_block:
    if '- {"ocr-primary": ["ocr-fallback", "rag-core"]}' in line:
        new_router_block.append('    - {"ocr-primary": ["ocr-fallback", "ocr-tier4", "rag-core"]}\n')
    elif '- {"ocr-fallback": ["rag-core"]}' in line:
        new_router_block.append('    - {"ocr-fallback": ["ocr-tier4", "rag-core"]}\n')
        new_router_block.append('    - {"ocr-tier4": ["rag-core"]}\n')
    else:
        new_router_block.append(line)

with open('litellm_config_fixed.yaml', 'w') as f:
    f.writelines(out)
    f.writelines(new_router_block)

