# --------------------------------------------------------------------------
# backend/services/asr_service.py — HTTP client wrapper for the ASR service
#
# Forwards audio files to the ASR Docker container for transcription.
# Used by the voice routes to convert speech to text.
# --------------------------------------------------------------------------

import httpx
import os

ASR_URL = os.getenv("ASR_URL", "http://asr:8004")


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> dict:
    """
    Send audio bytes to the ASR service and return transcribed text.

    Args:
        audio_bytes: Raw audio file bytes (WAV, WebM, MP3, etc.)
        filename: Original filename for format detection

    Returns:
        dict with "text" and "duration_ms" keys
    """
    async with httpx.AsyncClient(timeout=30) as client:
        files = {"file": (filename, audio_bytes)}
        response = await client.post(f"{ASR_URL}/transcribe", files=files)

        if response.status_code != 200:
            raise Exception(f"ASR service error: {response.status_code} {response.text}")

        return response.json()
