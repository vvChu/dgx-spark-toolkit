"""
AI Gateway Client — Python Module
Copy file này vào project để dùng ngay.

Usage:
    from ai_client import ai, chat, chat_stream

    # Quick chat
    reply = chat("Xin chào!")

    # Chọn model
    reply = chat("Explain REST API", model="claude-sonnet-4-6")

    # Streaming
    for chunk in chat_stream("Write quicksort in Python"):
        print(chunk, end="")

Requirements:
    pip install openai python-dotenv
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# --- Initialize client ---
ai = OpenAI(
    base_url=os.environ.get("AI_GATEWAY_URL", "http://100.83.192.30:8090/v1"),
    api_key=os.environ.get("AI_GATEWAY_KEY", os.environ.get("OPENAI_API_KEY", "")),
    timeout=120.0,
)

DEFAULT_MODEL = os.environ.get("AI_MODEL", "qwen-local-primary")


def chat(
    message: str,
    *,
    model: str = DEFAULT_MODEL,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Send a chat message and get a response."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": message})

    response = ai.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content


def chat_stream(
    message: str,
    *,
    model: str = DEFAULT_MODEL,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
):
    """Stream a chat response chunk by chunk."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": message})

    stream = ai.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            yield content


def chat_multi(
    messages: list[dict],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> str:
    """Send a full conversation (multiple messages) and get a response."""
    response = ai.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content


def list_models() -> list[str]:
    """List all available models on the gateway."""
    models = ai.models.list()
    return sorted(set(m.id for m in models.data))


# --- Demo / Self-test ---
if __name__ == "__main__":
    print(f"🔌 Gateway: {ai.base_url}")
    print(f"🤖 Default model: {DEFAULT_MODEL}")
    print()

    # List models
    print("📋 Available models:")
    for m in list_models():
        prefix = "🖥️ " if m in ("qwen-local-primary", "rag-core", "rag-light") else "☁️ "
        print(f"   {prefix} {m}")

    # Quick chat
    print()
    print("💬 Chat test:")
    reply = chat("Xin chào! Giới thiệu ngắn gọn về bạn.", max_tokens=100)
    print(f"   {reply}")

    # Streaming
    print()
    print("📡 Streaming test:")
    print("   ", end="")
    for chunk in chat_stream("Đếm từ 1 đến 5 bằng tiếng Việt.", max_tokens=50):
        print(chunk, end="", flush=True)
    print()
