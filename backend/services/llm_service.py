# --------------------------------------------------------------------------
# backend/services/llm_service.py — HTTP client wrapper for LM Studio
#
# Forwards chat messages to the LLM service (which wraps LM Studio).
# Supports both streaming and non-streaming modes.
# --------------------------------------------------------------------------

import httpx
import json
import os

LLM_URL = os.getenv("LLM_URL", "http://llm:8003")


async def generate_response(messages: list, stream: bool = False,
                            max_tokens: int = 300, temperature: float = 0.7) -> str:
    """
    Send messages to the LLM service and return the complete response text.
    Non-streaming mode — collects all tokens and returns full text.

    Args:
        messages: List of chat messages [{"role": "...", "content": "..."}]
        stream: Whether to use streaming (for voice, we use non-streaming)
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature

    Returns:
        Complete response text string
    """
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{LLM_URL}/generate",
            json={
                "messages": messages,
                "stream": stream,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )

        if response.status_code != 200:
            raise Exception(f"LLM service error: {response.status_code} {response.text}")

        if stream:
            # Collect streamed tokens into full text
            full_text = ""
            for line in response.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        full_text += data.get("token", "")
                    except json.JSONDecodeError:
                        continue
            return full_text
        else:
            result = response.json()
            return result.get("content", "")
