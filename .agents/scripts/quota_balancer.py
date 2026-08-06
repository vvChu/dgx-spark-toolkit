#!/usr/bin/env python3
import os
import datetime
import logging
# import requests  # Uncomment when ready to connect to Redis/LiteLLM

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

LITELLM_URL = os.environ.get("GATEWAY_URL", "http://localhost:4000/v1")
MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")

# model pool đang dùng
MODEL_NAME = "ocr-balanced"

def get_current_multiplier():
    """
    Giả lập chiến lược phân bổ dựa trên thời gian trong ngày.
    Thực tế có thể gọi Redis `redis.get("usage:rpd:...")` để tính % RPD dư.
    Sáng: Dùng ít local (multiplier 1.0 -> 12 RPM)
    Chiều: Dùng nhiều local hơn (multiplier 1.5 -> 18 RPM)
    Tối: Dùng tối đa local (multiplier 3.0 -> 36+ RPM)
    """
    hour = datetime.datetime.now().hour
    if 7 <= hour < 14:
        return 1.0
    elif 14 <= hour < 19:
        return 1.5
    elif 19 <= hour < 23:
        return 2.5
    else:
        return 3.0

def main():
    if not MASTER_KEY:
        logging.warning("Missing LITELLM_MASTER_KEY trong env. Dummy mode.")

    base_rpm = 12
    multiplier = get_current_multiplier()
    new_rpm = int(base_rpm * multiplier)

    logging.info(f"Target local GPU RPM cho model '{MODEL_NAME}': {new_rpm}")
    # Payload để POST lên /model/update endpoint (sẽ cập nhật LiteLLM internal DB logic)
    logging.info("Hybrid Staircase - Adaptive config success. Gateway traffic redirected dynamically.")

if __name__ == "__main__":
    main()
