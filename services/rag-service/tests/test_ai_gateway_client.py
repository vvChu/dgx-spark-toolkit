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
        parsed = client._clean_and_parse_json(raw, schema=SampleMetadata)
        assert parsed["title"] == "Sample"
        assert parsed["category"] == "Legal"

    def test_extract_json_embedded_fences_and_text(self):
        client = AIGatewayClient()
        raw = "Here is the result:\n```json\n{\"title\": \"QCVN 06:2022\", \"category\": \"TCVN\"}\n```\nHope this helps!"
        parsed = client._clean_and_parse_json(raw)
        assert parsed["title"] == "QCVN 06:2022"
        assert parsed["category"] == "TCVN"

    def test_mock_client_extract_json(self):
        mock_client = MockAIGatewayClient()
        data = mock_client.extract_json_sync("Extract metadata prompt", schema=SampleMetadata)
        assert isinstance(data, dict)
        assert "title" in data
        assert "category" in data
