import os
import shutil

# Staging area
src_dir = "/tmp/vllm_backport"
dst_dir = "/home/vvc/Codebase/dgx-spark-toolkit/vllm_backport"
os.makedirs(dst_dir, exist_ok=True)

# Files to backport
files = ["qwen3_moe.py", "qwen3_vl_moe.py", "qwen3_vl.py"]

# Shim import to add to the top of files
shim_import = "import vllm_shim\n"

for filename in files:
    src_path = os.path.join(src_dir, filename)
    dst_path = os.path.join(dst_dir, filename)
    
    if not os.path.exists(src_path):
        print(f"Source file not found: {src_path}")
        continue
        
    with open(src_path, "r") as f:
        lines = f.readlines()
    
    # Insert shim at the top (after docstrings/comments)
    # Find the first real import or code
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith('"""'):
            insert_idx = i
            break
    
    new_lines = lines[:insert_idx] + [shim_import] + lines[insert_idx:]
    
    # Apply surgical patches to the lines
    final_lines = []
    for line in new_lines:
        # 1. Strip 'model.' prefix in load_weights
        if "for name, loaded_weight in weights:" in line:
            final_lines.append(line)
            indent = line[:line.find("for")] + "    "
            final_lines.append(f"{indent}name = name.removeprefix('model.language_model.').removeprefix('model.')\n")
            continue
            
        # 2. Fix relative imports (from . interfaces -> from vllm.model_executor.models.interfaces)
        if "from .interfaces" in line:
            line = line.replace("from .interfaces", "from vllm.model_executor.models.interfaces")
        if "from .qwen3_moe" in line:
            line = line.replace("from .qwen3_moe", "from vllm.model_executor.models.qwen3_moe")
        if "from .qwen3_vl" in line:
            line = line.replace("from .qwen3_vl", "from vllm.model_executor.models.qwen3_vl")
            
        # 3. Safe config access
        line = line.replace("config.norm_topk_prob", "getattr(config, 'norm_topk_prob', True)")
        line = line.replace("config.decoder_sparse_step", "getattr(config, 'decoder_sparse_step', 4)")
        
        # 4. Handle V1 specific imports if they crash (we shimmed the module, but let's be safe)
        if "from vllm.sequence import IntermediateTensors" in line:
            line = "from vllm_shim import Dummy as IntermediateTensors # Shimmed\n"

        final_lines.append(line)
        
    with open(dst_path, "w") as f:
        f.writelines(final_lines)
    print(f"Backported and patched {filename} to {dst_path}")

print("Backport staging complete.")
