import logging
import httpx
import os
from typing import List, Optional
from core.config import get_settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        settings = get_settings()
        self.token = settings.TELEGRAM_BOT_TOKEN.get_secret_value()
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.enabled = bool(self.token and self.chat_id)

    async def send_message(self, text: str):
        """Send a message to Telegram asynchronously."""
        if not self.enabled:
            logger.warning("Telegram notification skipped: Credentials not configured.")
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                }
                response = await client.post(self.api_url, json=payload)
                response.raise_for_status()
                logger.info("Telegram notification sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

    async def notify_milestone(self, count: int, files: List[str]):
        """Notify user about a processing milestone with document list."""
        header = f"🚀 <b>INGESTION PROGRESS UPDATE</b>\n\n"
        milestone_text = f"✅ Đã xử lý thêm <b>50 tài liệu</b> (Tổng cộng: {count})\n\n"
        doc_list = "<b>Danh sách 50 tài liệu vừa hoàn tất:</b>\n"

        # Format the list with bullet points
        items = [f"• {os.path.basename(f)}" for f in files]
        full_list = "\n".join(items)

        # Telegram has a 4096 char limit, truncate if necessary
        message = header + milestone_text + doc_list + full_list
        if len(message) > 4000:
            message = message[:3997] + "..."

        await self.send_message(message)


# Global instance
import os
notifier = TelegramNotifier()
