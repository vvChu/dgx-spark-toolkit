import sys
import torch
from unittest.mock import MagicMock

# Create dummy modules for missing parts in 0.14.x
class Dummy:
    def __init__(self, *args, **kwargs): pass
    def __call__(self, *args, **kwargs): return args[0] if args else None

def support_torch_compile(func):
    return func

# Shim compilation decorators
compilation = MagicMock()
compilation.decorators = MagicMock()
compilation.decorators.support_torch_compile = support_torch_compile
sys.modules["vllm.compilation"] = compilation
sys.modules["vllm.compilation.decorators"] = compilation.decorators

# Shim config
import vllm.config
if not hasattr(vllm.config, "get_current_vllm_config"):
    vllm.config.get_current_vllm_config = lambda: None

# Shim IntermediateTensors
sequence = MagicMock()
sequence.IntermediateTensors = Dummy
sys.modules["vllm.sequence"] = sequence

# Shim maybe_remap_kv_scale_name if missing
import vllm.model_executor.model_loader.weight_utils as wu
if not hasattr(wu, "maybe_remap_kv_scale_name"):
    wu.maybe_remap_kv_scale_name = lambda name, params_dict: name

# SharedFusedMoE - this is the most likely to cause issues if structural differences are large
# We'll try to map it to FusedMoE or similar if possible, or just mock it if it's not used in 122B
import vllm.model_executor.layers.fused_moe as fm
if not hasattr(fm, "SharedFusedMoE"):
    fm.SharedFusedMoE = Dummy
    print("Warning: SharedFusedMoE mocked. This might cause issues if model uses shared experts.")

print("vLLM Shims applied successfully.")
