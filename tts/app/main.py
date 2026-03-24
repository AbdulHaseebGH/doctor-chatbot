# --------------------------------------------------------------------------
# tts/app/main.py — Text-to-Speech Service using piper-tts
#
# Provides a POST /synthesize endpoint that converts text to speech audio.
# Uses piper-tts which is extremely fast on CPU (~10x real-time speed),
# making it ideal for low-latency voice applications.
#
# Voice: en_US-lessac-medium — clear American English, natural prosody.
# Target: <300ms for first audio chunk on CPU.
# --------------------------------------------------------------------------

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import subprocess, tempfile, os, time, io, wave, struct

app = FastAPI(title="TTS Service — piper-tts")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Piper model configuration
# ---------------------------------------------------------------------------
MODEL_PATH = os.getenv("PIPER_MODEL", "/models/piper/en_US-lessac-medium.onnx")
print(f"[TTS] Using piper model: {MODEL_PATH}")


class SynthesizeRequest(BaseModel):
    text: str


@app.get("/health")
async def health():
    """Health check — confirms service is ready."""
    return {"status": "ok", "service": "tts", "model": os.path.basename(MODEL_PATH)}


@app.post("/synthesize")
async def synthesize(request: SynthesizeRequest):
    """
    Convert text to speech audio using piper-tts.

    Accepts: { "text": "Hello, how can I help you?" }
    Returns: WAV audio stream (16-bit PCM, 22050 Hz)

    Piper runs as a subprocess and pipes raw PCM which we wrap in a WAV header
    and stream back. The first audio bytes arrive within ~200ms on CPU.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="No text provided")

    text = request.text.strip()

    # Limit text length to prevent abuse and keep latency low
    if len(text) > 1000:
        text = text[:1000]

    start = time.time()

    try:
        # Run piper as subprocess — it reads text from stdin, writes raw PCM to stdout
        # --output-raw gives us raw 16-bit PCM at 22050 Hz (single channel)
        proc = subprocess.run(
            [
                "piper",
                "--model", MODEL_PATH,
                "--output-raw",
            ],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )

        if proc.returncode != 0:
            error_msg = proc.stderr.decode("utf-8", errors="replace")
            print(f"[TTS] Piper error: {error_msg}")
            raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {error_msg}")

        raw_pcm = proc.stdout
        elapsed_ms = int((time.time() - start) * 1000)
        print(f"[TTS] Synthesized {len(text)} chars in {elapsed_ms}ms ({len(raw_pcm)} bytes PCM)")

        # Wrap raw PCM in a WAV header so browsers can play it natively
        sample_rate = 22050
        channels = 1
        sample_width = 2  # 16-bit

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(raw_pcm)

        wav_buffer.seek(0)

        return StreamingResponse(
            wav_buffer,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "inline; filename=speech.wav",
                "X-Synthesis-Time-Ms": str(elapsed_ms),
            },
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="TTS synthesis timed out")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[TTS] Error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")
