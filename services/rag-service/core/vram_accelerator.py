import threading
import contextlib
import logging

logger = logging.getLogger(__name__)

# Global lock to ensure only one task can move a large model to VRAM at a time
GPU_INFERENCE_LOCK = threading.Lock()

@contextlib.contextmanager
def vram_accelerate(huggingface_wrapper, min_vram_gb: float = 4.0):
    """
    Context manager to dynamically move a PyTorch model to GPU if enough VRAM is available.
    Moves the model back to CPU and clears cache upon exit.
    
    Args:
        huggingface_wrapper: The wrapper object (e.g. BGEM3FlagModel or CrossEncoder)
        min_vram_gb: Minimum free VRAM in GB required to offload to GPU.
    """
    import torch
    
    # Check if GPU is available
    if not torch.cuda.is_available():
        yield False
        return
        
    try:
        device_id = torch.cuda.current_device()
        free_mem, _ = torch.cuda.mem_get_info(device_id)
        free_gb = free_mem / (1024 ** 3)
    except Exception as e:
        logger.warning(f"Could not check VRAM: {e}")
        free_gb = 0.0
    
    # If we have enough VRAM, try to acquire the GPU usage lock non-blockingly
    if free_gb >= min_vram_gb:
        acquired = GPU_INFERENCE_LOCK.acquire(blocking=False)
        if acquired:
            old_device_attr = getattr(huggingface_wrapper, 'device', None)
            old_target_device = getattr(huggingface_wrapper, '_target_device', None)
            try:
                # Move underlying PyTorch model to GPU
                if hasattr(huggingface_wrapper, 'model'):
                    huggingface_wrapper.model.to('cuda')
                
                # Patch attributes indicating target device so inputs are sent to GPU
                if old_device_attr is not None:
                    huggingface_wrapper.device = 'cuda'
                if old_target_device is not None:
                    huggingface_wrapper._target_device = 'cuda'
                    
                # logger.debug(f"[VRAM Accel] Offloading to GPU. Free VRAM: {free_gb:.1f}GB")
                yield True
            except Exception as e:
                logger.error(f"[VRAM Accel] Error during GPU acceleration: {e}")
                yield False
            finally:
                # Revert attributes
                if old_device_attr is not None:
                    huggingface_wrapper.device = old_device_attr
                if old_target_device is not None:
                    huggingface_wrapper._target_device = old_target_device
                
                # Revert PyTorch model to CPU and clear Cache
                if hasattr(huggingface_wrapper, 'model'):
                    huggingface_wrapper.model.to('cpu')
                torch.cuda.empty_cache()
                GPU_INFERENCE_LOCK.release()
                # logger.debug(f"[VRAM Accel] Returned model to CPU.")
            return

    # Fallback to CPU if not enough VRAM or lock is taken
    # logger.debug(f"[VRAM Accel] Falling back to bare CPU. Free VRAM: {free_gb:.1f}GB. Lock state: {GPU_INFERENCE_LOCK.locked()}")
    yield False
