"""GPU VRAM Manager for context-managed VRAM allocation & health monitoring.

Manages dynamic PyTorch GPU offloading with non-blocking VRAM checks,
mutex locking for concurrent model execution, and VRAM health monitoring.
"""
import contextlib
import logging
import os
import threading
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class GPUResourceManager:
    """Singleton/Instance GPU VRAM Manager for model offloading."""

    _instance: Optional["GPUResourceManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.inference_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "GPUResourceManager":
        """Get or create singleton GPUResourceManager instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_vram_info(self) -> Tuple[float, float, bool]:
        """Check free & total GPU memory in GB.

        On Linux Unified Memory systems (NVIDIA Blackwell GB10),
        torch.cuda.mem_get_info() only reports unmapped physical free pages (MemFree),
        ignoring reclaimable memory and available host RAM. We inspect MemAvailable
        and container cgroup limits to determine actual allocation headroom.

        Returns:
            Tuple of (free_or_available_gb, total_gb, is_available).
        """
        try:
            import torch
            if not torch.cuda.is_available():
                return 0.0, 0.0, False

            # Blackwell Unified Memory headroom detection
            host_avail_gb: Optional[float] = None
            total_gb: Optional[float] = None
            if os.path.exists("/proc/meminfo"):
                try:
                    with open("/proc/meminfo", "r") as f:
                        for line in f:
                            if line.startswith("MemAvailable:"):
                                host_avail_gb = int(line.split()[1]) / (1024 ** 2)
                            elif line.startswith("MemTotal:"):
                                total_gb = int(line.split()[1]) / (1024 ** 2)
                except Exception as ex:
                    logger.debug("Could not read /proc/meminfo: %s", ex)

            cgroup_avail_gb = float("inf")
            if os.path.exists("/sys/fs/cgroup/memory.max") and os.path.exists("/sys/fs/cgroup/memory.current"):
                try:
                    with open("/sys/fs/cgroup/memory.max", "r") as f:
                        max_str = f.read().strip()
                    with open("/sys/fs/cgroup/memory.current", "r") as f:
                        cur_str = f.read().strip()
                    if max_str != "max":
                        cgroup_avail_gb = max(0.0, (int(max_str) - int(cur_str)) / (1024 ** 3))
                except Exception as ex:
                    logger.debug("Could not read cgroup limits: %s", ex)

            if host_avail_gb is not None:
                effective_free = min(host_avail_gb, cgroup_avail_gb)
                return effective_free, total_gb or 128.0, True

            device_id = torch.cuda.current_device()
            free_mem, total_mem = torch.cuda.mem_get_info(device_id)
            return (
                free_mem / (1024 ** 3),
                total_mem / (1024 ** 3),
                True,
            )
        except Exception as e:
            logger.warning("Could not query GPU VRAM: %s", e)
            return 0.0, 0.0, False

    @contextlib.contextmanager
    def allocate(
        self,
        huggingface_wrapper: Any,
        min_vram_gb: float = 4.0,
    ):
        """Context manager to dynamically move PyTorch model to GPU.

        Args:
            huggingface_wrapper: Wrapper (e.g. BGEM3FlagModel, CrossEncoder).
            min_vram_gb: Minimum free VRAM in GB required to offload to GPU.
        """
        free_gb, _, available = self.get_vram_info()
        if not available or free_gb < min_vram_gb:
            yield False
            return

        acquired = self.inference_lock.acquire(blocking=False)
        if not acquired:
            yield False
            return

        import torch

        old_device_attr = getattr(huggingface_wrapper, "device", None)
        old_target_device = getattr(
            huggingface_wrapper, "_target_device", None
        )
        old_target_devices = getattr(
            huggingface_wrapper, "target_devices", None
        )

        try:
            if hasattr(huggingface_wrapper, "to") and callable(huggingface_wrapper.to):
                huggingface_wrapper.to("cuda")
            elif hasattr(huggingface_wrapper, "model") and hasattr(huggingface_wrapper.model, "to"):
                huggingface_wrapper.model.to("cuda")

            if not hasattr(huggingface_wrapper, "to"):
                if old_device_attr is not None:
                    try:
                        huggingface_wrapper.device = "cuda"
                    except (AttributeError, TypeError):
                        pass
                if old_target_devices is not None:
                    try:
                        huggingface_wrapper.target_devices = ["cuda"]
                    except (AttributeError, TypeError):
                        pass

            yield True
        except Exception as e:
            logger.error("[GPUManager] Error during GPU acceleration: %s", e)
            yield False
        finally:
            if not hasattr(huggingface_wrapper, "to"):
                if old_device_attr is not None:
                    try:
                        huggingface_wrapper.device = old_device_attr
                    except (AttributeError, TypeError):
                        pass
                if old_target_devices is not None:
                    try:
                        huggingface_wrapper.target_devices = old_target_devices
                    except (AttributeError, TypeError):
                        pass

            if hasattr(huggingface_wrapper, "to") and callable(huggingface_wrapper.to):
                try:
                    huggingface_wrapper.to("cpu")
                except Exception:
                    pass
            elif hasattr(huggingface_wrapper, "model") and hasattr(huggingface_wrapper.model, "to"):
                try:
                    huggingface_wrapper.model.to("cpu")
                except Exception:
                    pass

            try:
                torch.cuda.empty_cache()
            except Exception:
                pass

            self.inference_lock.release()

    def health_check(self) -> Dict[str, Any]:
        """Return structured health status of GPU resources."""
        free_gb, total_gb, available = self.get_vram_info()
        return {
            "gpu_available": available,
            "free_vram_gb": round(free_gb, 2),
            "total_vram_gb": round(total_gb, 2),
            "is_locked": self.inference_lock.locked(),
        }


# Backwards compatibility function
def vram_accelerate(huggingface_wrapper: Any, min_vram_gb: float = 4.0):
    """Legacy helper wrapping GPUResourceManager.allocate()."""
    manager = GPUResourceManager.get_instance()
    return manager.allocate(huggingface_wrapper, min_vram_gb=min_vram_gb)
