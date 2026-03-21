from openai import OpenAI
from pydantic import BaseModel
from typing import List, Dict, Union
import base64
import os

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
    def __init__(self):
        # Point natively to the AI Gateway container
        self.gateway_url = os.environ.get("VLLM_API_BASE", "http://ai-gateway:4000/v1")
        api_key = os.environ.get("LITELLM_MASTER_KEY")
        if not api_key:
            raise RuntimeError(
                "LITELLM_MASTER_KEY environment variable is required for RAGRouter."
            )
        self.api_key = api_key
        self.client = OpenAI(base_url=self.gateway_url, api_key=self.api_key)

    def process(self, text: str):
        """Structured JSON Metadata Extraction via Pydantic"""
        system_prompt = "Bạn là chuyên gia pháp lý VN. Trích xuất thông tin thành JSON chuẩn xác. Không giải thích."

        response = self.client.chat.completions.create(
            model=os.environ.get("VLLM_MODEL", "rag-core"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{text[:200000]}"}
            ],
            temperature=0.1, # Maximized determinism
            max_tokens=2048,
            # Force JSON strictly using Pydantic schema
            response_format={"type": "json_schema", "json_schema": {"name": "metadata_schema", "strict": True, "schema": LegalMetadata.model_json_schema()}}
        )
        raw_res = response.choices[0].message.content
        try:
            # Validate output matches structure to ensure high KG accuracy
            validated = LegalMetadata.model_validate_json(raw_res)
            return validated.model_dump()
        except Exception as e:
            return {"error": "Validation failed", "raw": raw_res}

    def get_embedding(self, text: str, dimensions: int = 1024):
        """Embedding function - Sử dụng BGE-M3 hybrid embedding model."""
        from services.retrieval_service import get_embedding_model
        model = get_embedding_model()
        return model.embed_query(text)["dense"]

    def ocr_vision(self, image_path: str):
        """OCR với native vision - Gửi ảnh trực tiếp"""
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode("utf-8")
        
        response = self.client.chat.completions.create(
            model="qwen3.5-9b-rag",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Trích xuất toàn bộ văn bản tiếng Việt từ ảnh pháp lý này một cách chính xác nhất, giữ nguyên layout và bảng biểu."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=4096,
            temperature=0.0
        )
        return response.choices[0].message.content
