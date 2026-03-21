import asyncio
import httpx
import time
from core.config import get_settings

async def test_llm():
    settings = get_settings()
    url = f"{settings.VLLM_API_BASE}/models"
    headers = {"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY.get_secret_value()}"}
    
    print(f"Testing URL: {url}")
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            print(f"Status: {resp.status_code}")
            print(f"Time: {time.time() - start:.2f}s")
            print(f"Response: {resp.text[:100]}...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_llm())
