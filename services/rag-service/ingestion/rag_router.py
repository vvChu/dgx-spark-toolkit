"""RAGRouter using unified AIGatewayClient."""
from typing import List, Dict, Union, Any
from pydantic import BaseModel
from core.ai_gateway_client import AIGatewayClient


class LegalMetadata(BaseModel):
    title: str
    issue_date: str
    effective_date: str
    authority: str
    document_type: str
    keywords: List[str]
    summary: str
    relations: List[Dict[str, str]]


class RAGRouter:
    def __init__(self, gateway_client: AIGatewayClient | None = None):
        self.client = gateway_client or AIGatewayClient()

    def process(self, text: str) -> Dict[str, Any]:
        """Structured JSON Metadata Extraction via Pydantic using AIGatewayClient"""
        system_prompt = "Bạn là chuyên gia pháp lý VN. Trích xuất thông tin thành JSON chuẩn xác. Không giải thích."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{text[:200000]}"}
        ]
        try:
            return self.client.complete_json_sync(messages, schema=LegalMetadata)
        except Exception as e:
            return {"error": str(e)}

    def get_embedding(self, text: str, dimensions: int = 1024) -> List[float]:
        """Embedding function - Sử dụng BGE-M3 hybrid embedding model."""
        from retrieval.search_pipeline import get_embedding_model
        model = get_embedding_model()
        res = model.embed_query(text)
        return res.get("dense", []) if isinstance(res, dict) else res

    def ocr_vision(self, image_path: str) -> str:
        """OCR với native vision sử dụng AIGatewayClient"""
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        return self.client.complete_vision_sync(image_bytes, prompt="Trích xuất toàn bộ văn bản tiếng Việt từ ảnh pháp lý này một cách chính xác nhất, giữ nguyên layout và bảng biểu.")
