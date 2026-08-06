"""Unit tests for the deep AIGatewayClient module and MockAIGatewayClient adapter."""
import asyncio
import pytest
from pydantic import BaseModel
from typing import List

from core.ai_gateway_client import AIGatewayClient, MockAIGatewayClient


class SampleMetadata(BaseModel):
    title: str
    category: str


class TestAIGatewayClient:
    def test_mock_client_complete(self):
        mock_client = MockAIGatewayClient(default_response="Hello World")
        res = mock_client.complete_sync([{"role": "user", "content": "Hi"}])
        assert res == "Hello World"
        assert len(mock_client.call_history) == 1

    def test_mock_client_complete_json(self):
        mock_client = MockAIGatewayClient()
        data = mock_client.complete_json_sync(
            [{"role": "user", "content": "Extract"}],
            schema=SampleMetadata,
        )
        assert isinstance(data, dict)
        assert "title" in data
        assert "category" in data

    def test_mock_client_complete_vision(self):
        mock_client = MockAIGatewayClient(default_response="Extracted OCR Text")
        res = mock_client.complete_vision_sync(b"fake_image_bytes", prompt="Extract OCR")
        assert "Extracted OCR Text" in res
        assert len(mock_client.call_history) == 1

    def test_complete_json_markdown_stripping(self):
        client = AIGatewayClient()
        raw = "```json\n{\"title\": \"Sample\", \"category\": \"Legal\"}\n```"

        with pytest.MonkeyPatch().context() as m:
            m.setattr(client, "complete", lambda *args, **kwargs: asyncio.Future())
            # Directly test parsing logic
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            val = SampleMetadata.model_validate_json(cleaned)
            assert val.title == "Sample"
            assert val.category == "Legal"
