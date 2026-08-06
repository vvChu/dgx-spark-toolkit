import os
import sys
from pprint import pprint

# Setup path for imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Force test settings
os.environ["GPU_MAX_CONCURRENCY"] = "2"
os.environ["OOM_PROTECTION"] = "true"

from ingestion.concurrency import gpu_semaphore, acquire_gpu

print("Testing adaptive concurrency...")
adaptive_val = gpu_semaphore._get_adaptive_concurrency()
print(f"Adaptive concurrency returned: {adaptive_val}")

print("\nTesting Lock Acquire...")
owner_1 = gpu_semaphore.acquire(timeout=1)
owner_2 = gpu_semaphore.acquire(timeout=1)
owner_3 = gpu_semaphore.acquire(timeout=1)

print(f"Lock 1: {owner_1}")
print(f"Lock 2: {owner_2}")
print(f"Lock 3 (should fail): {owner_3}")

print("\nTesting Release...")
gpu_semaphore.release(owner_1)
owner_3_retry = gpu_semaphore.acquire(timeout=1)
print(f"Lock 3 retry (should succeed): {owner_3_retry}")

# Clean up
gpu_semaphore.release(owner_2)
gpu_semaphore.release(owner_3_retry)
print("\nDone.")
