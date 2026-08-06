import os
import time
import uuid
import logging
import redis
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# LUA Scripts for Distributed Semaphore using Sorted Set
# KEYS[1] = ZSET key name
# ARGV[1] = max concurrency
# ARGV[2] = current timestamp
# ARGV[3] = TTL in seconds
# ARGV[4] = unique owner ID
ACQUIRE_SCRIPT = """
redis.call('zremrangebyscore', KEYS[1], '-inf', ARGV[2])
local current_count = redis.call('zcard', KEYS[1])
if current_count < tonumber(ARGV[1]) then
    redis.call('zadd', KEYS[1], tonumber(ARGV[2]) + tonumber(ARGV[3]), ARGV[4])
    return 1
else
    return 0
end
"""

RELEASE_SCRIPT = """
redis.call('zrem', KEYS[1], ARGV[1])
return 1
"""

class GPUSemaphore:
    """Distributed Semaphore for regulating concurrent access to Local GPU resources.
    
    Includes an OS-level safeguard: If System Mailable RAM falls below the threshold,
    the effective concurrency is immediately squeezed to 0, forcing failsafe overflow to Cloud.
    """
    
    def __init__(self, key="gpu_ocr_semaphore"):
        self.key = key
        url = os.environ.get("REDIS_URL", "redis://litellm-redis:6379/1")
        self.redis = redis.from_url(url, decode_responses=True)
        self._acquire_sha = self.redis.script_load(ACQUIRE_SCRIPT)
        self._release_sha = self.redis.script_load(RELEASE_SCRIPT)
        
    def _get_adaptive_concurrency(self) -> int:
        """Calculate dynamic concurrency based on system health."""
        # 1. Check if OOM Protection is enabled
        from ingestion.pipeline_config import OOM_PROTECTION_ENABLED, OS_RAM_SAFE_MARGIN_MB, GPU_MAX_CONCURRENCY
        
        if not OOM_PROTECTION_ENABLED:
            return GPU_MAX_CONCURRENCY
            
        # 2. Check /proc/meminfo
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
            for line in meminfo.splitlines():
                if line.startswith("MemAvailable:"):
                    # Extract KB and convert to MB
                    available_kb = int(line.split()[1])
                    available_mb = available_kb // 1024
                    
                    if available_mb < OS_RAM_SAFE_MARGIN_MB:
                        logger.warning(
                            f"[OOM WATCHER] System RAM dangerously low ({available_mb}MB < {OS_RAM_SAFE_MARGIN_MB}MB). "
                            "Forcing GPU_MAX_CONCURRENCY = 0 to prevent crash."
                        )
                        return 0  # Cloud-only mode
                    break
        except Exception as e:
            logger.debug(f"Could not read /proc/meminfo for OOM protection: {e}")
            
        return GPU_MAX_CONCURRENCY

    def acquire(self, timeout=0) -> str | None:
        """Attempt to acquire the semaphore. Returns a unique owner_id if successful, else None."""
        max_concurrency = self._get_adaptive_concurrency()
        
        # If disabled by OOM watcher, fail immediately
        if max_concurrency <= 0:
            return None
            
        owner_id = str(uuid.uuid4())
        start_time = time.time()
        ttl = 150  # 150 seconds expiration for orphaned locks
        
        while True:
            now = time.time()
            result = self.redis.evalsha(
                self._acquire_sha, 1, self.key, 
                max_concurrency, int(now), ttl, owner_id
            )
            
            if result == 1:
                return owner_id
                
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return None
                
            time.sleep(0.5)

    def release(self, owner_id: str):
        """Release the semaphore slot belonging to owner_id."""
        if not owner_id:
            return
        try:
            self.redis.evalsha(self._release_sha, 1, self.key, owner_id)
        except Exception as e:
            logger.error(f"Failed to release GPU semaphore: {e}")

# Global singleton instance
gpu_semaphore = GPUSemaphore()

@contextmanager
def acquire_gpu(timeout=0):
    """Context manager for easy semaphore usage."""
    owner_id = gpu_semaphore.acquire(timeout=timeout)
    acquired = owner_id is not None
    try:
        yield acquired
    finally:
        if acquired:
            gpu_semaphore.release(owner_id)
