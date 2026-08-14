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

    def test_mock_client_complete_vision_with_system_prompt(self):
        mock_client = MockAIGatewayClient(default_response="Extracted Table OCR")
        res = mock_client.complete_vision_sync(
            b"fake_image_bytes",
            prompt="Extract OCR",
            system_prompt="Custom Legal OCR System Prompt",
        )
        assert "Extracted Table OCR" in res
        assert len(mock_client.call_history) == 1
        assert mock_client.call_history[0]["system_prompt"] == "Custom Legal OCR System Prompt"

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

    def test_tiered_router_estimation_text_and_vision(self):
        import sys
        from pathlib import Path
        gateway_dir = str(Path(__file__).resolve().parents[2] / "ai-gateway")
        if gateway_dir not in sys.path:
            sys.path.insert(0, gateway_dir)

        from custom_callbacks import ParameterNormalizer, _estimate_tokens_and_has_vision

        text_messages = [{"role": "user", "content": "Hello world " * 50}]
        tokens, has_vision = _estimate_tokens_and_has_vision(text_messages)
        assert tokens > 0
        assert has_vision is False

        # Verify ParameterNormalizer class method directly
        tokens_direct, has_vision_direct = ParameterNormalizer.estimate_tokens_and_has_vision(text_messages)
        assert tokens_direct == tokens
        assert has_vision_direct is False

        vision_messages = [
            {"role": "user", "content": [{"type": "text", "text": "OCR"}, {"type": "image_url", "image_url": "data:image/png"}]}
        ]
        _, vision_flag = _estimate_tokens_and_has_vision(vision_messages)
        assert vision_flag is True

    def test_tiered_router_pre_call_hook_routing(self):
        import sys
        import asyncio
        from pathlib import Path
        gateway_dir = str(Path(__file__).resolve().parents[2] / "ai-gateway")
        if gateway_dir not in sys.path:
            sys.path.insert(0, gateway_dir)

        from custom_callbacks import GeminiParameterCorrector, ParameterNormalizer

        # Test ParameterNormalizer pure function directly
        req_data = {
            "model": "text-auto",
            "messages": [{"role": "user", "content": "Short query"}]
        }
        res_pure = ParameterNormalizer.normalize_request(req_data)
        assert res_pure["model"] == "openai/gemma-4-26b-a4b-it"

        # Test adapter async hook
        corrector = GeminiParameterCorrector()
        res = asyncio.run(corrector.async_pre_call_hook({}, req_data))
        assert res["model"] == "openai/gemma-4-26b-a4b-it"

        # Long text prompt (> 500 tokens = > 2000 chars) -> Should route to Gemini 3.5 Flash Lite
        long_text = "Detailed legal analysis request. " * 100
        req_data_long = {
            "model": "text-auto",
            "messages": [{"role": "user", "content": long_text}]
        }
        res_long = asyncio.run(corrector.async_pre_call_hook({}, req_data_long))
        assert res_long["model"] == "gemini/gemini-3.5-flash-lite"

    def test_key_cooldown_manager_and_rotation(self):
        import sys
        import asyncio
        from pathlib import Path
        gateway_dir = str(Path(__file__).resolve().parents[2] / "ai-gateway")
        if gateway_dir not in sys.path:
            sys.path.insert(0, gateway_dir)

        from custom_callbacks import KeyCooldownManager, GeminiParameterCorrector

        local_cooldown_mgr = KeyCooldownManager(cooldown_seconds=60)

        # Test marking cooldown
        key = "AIzaSyTestKey12345"
        assert not local_cooldown_mgr.is_key_in_cooldown(key)
        local_cooldown_mgr.mark_key_cooldown(key)
        assert local_cooldown_mgr.is_key_in_cooldown(key)

        # Test failure event logging triggers cooldown
        corrector = GeminiParameterCorrector()
        asyncio.run(
            corrector.async_log_failure_event(
                {"status_code": 429, "api_key": "AIzaSy429Key67890"},
                None,
                0,
                1,
            )
        )
        from custom_callbacks import key_cooldown_manager
        assert key_cooldown_manager.is_key_in_cooldown("AIzaSy429Key67890")

    def test_mock_client_stream_default(self):
        import asyncio
        from core.ai_gateway_client import StreamChunk

        async def _test():
            mock_client = MockAIGatewayClient(default_response="Xin chào Việt Nam")
            tokens = []
            async for chunk in mock_client.stream([{"role": "user", "content": "Hi"}]):
                assert isinstance(chunk, StreamChunk)
                assert chunk.is_thought is False
                tokens.append(chunk.text)

            assert "".join(tokens) == "Xin chào Việt Nam"
            assert len(mock_client.call_history) == 1
            assert mock_client.call_history[0]["stream"] is True

        asyncio.run(_test())

    def test_mock_client_stream_custom_chunks_with_thought(self):
        import asyncio
        from core.ai_gateway_client import StreamChunk

        async def _test():
            mock_client = MockAIGatewayClient()
            custom = [
                StreamChunk(text="Phân tích Điều 5...", is_thought=True),
                StreamChunk(text=" ", is_thought=True),
                StreamChunk(text="Theo quy định tại Điều 5", is_thought=False),
            ]
            received = []
            async for chunk in mock_client.stream([{"role": "user", "content": "Query"}], custom_chunks=custom):
                received.append(chunk)

            assert len(received) == 3
            assert received[0].is_thought is True
            assert received[0].text == "Phân tích Điều 5..."
            assert received[2].is_thought is False
            assert received[2].text == "Theo quy định tại Điều 5"

        asyncio.run(_test())

    def test_mock_client_set_mock_vision_response_string(self):
        mock_client = MockAIGatewayClient()
        mock_client.set_mock_vision_response("| Cột 1 | Cột 2 |\n|---|---|\n| A | B |")
        res = mock_client.complete_vision_sync(b"fake_table_png", prompt="Convert table")
        assert "| Cột 1 | Cột 2 |" in res

    def test_mock_client_set_mock_vision_response_callable(self):
        mock_client = MockAIGatewayClient()
        mock_client.set_mock_vision_response(lambda prompt, img: f"Dynamically handled prompt: {prompt}")
        res = mock_client.complete_vision_sync(b"image_bytes", prompt="Extract Điều 1")
        assert res == "Dynamically handled prompt: Extract Điều 1"
