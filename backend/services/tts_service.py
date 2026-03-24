# --------------------------------------------------------------------------
# backend/services/tts_service.py — HTTP client wrapper for the TTS service
#
# Forwards text to the TTS Docker container for speech synthesis.
# Used by the voice routes to convert LLM response text to audio.
# --------------------------------------------------------------------------

import httpx
import os

TTS_URL = os.getenv("TTS_URL", "http://tts:8005")


async def synthesize_speech(text: str) -> bytes:
    """
    Send text to the TTS service and return WAV audio bytes.

    Args:
        text: Text to synthesize into speech

    Returns:
        WAV audio bytes
    """
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{TTS_URL}/synthesize",
            json={"text": text},
        )

        if response.status_code != 200:
            raise Exception(f"TTS service error: {response.status_code} {response.text}")

        return response.content
