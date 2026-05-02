# --------------------------------------------------------------------------
# asr/app/main.py — Dual ASR Service
#
# POST /transcribe  → faster-whisper (batch, high quality, primary endpoint)
# WS  /ws/asr-stream → Vosk (real-time streaming with VAD silence detection)
#
# Phase 0: Both engines coexist. Whisper = quality batch. Vosk = low-latency stream.
# --------------------------------------------------------------------------

import os
import tempfile
import time
import json
import asyncio

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ASR Service — faster-whisper (batch) + Vosk (streaming)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# FASTER-WHISPER — loaded once at startup (batch transcription)
# ---------------------------------------------------------------------------
from faster_whisper import WhisperModel

MODEL_SIZE = os.getenv("MODEL_SIZE", "base")
whisper_model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
print(f"[ASR] Loaded faster-whisper model: {MODEL_SIZE} (int8, CPU)")

# ---------------------------------------------------------------------------
# VOSK — loaded once at startup (streaming ASR)
# ---------------------------------------------------------------------------
from vosk import Model as VoskModel, KaldiRecognizer

VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "/app/models/vosk-model-en")
VOSK_SAMPLE_RATE = 16000  # 16kHz raw PCM expected from browser

try:
    vosk_model = VoskModel(VOSK_MODEL_PATH)
    print(f"[ASR] Loaded Vosk model from {VOSK_MODEL_PATH}")
    VOSK_AVAILABLE = True
except Exception as e:
    print(f"[ASR] Vosk model NOT available: {e}")
    VOSK_AVAILABLE = False
    vosk_model = None

# ---------------------------------------------------------------------------
# VAD silence threshold — chunks with energy below this are treated as silence
# ---------------------------------------------------------------------------
SILENCE_ENERGY_THRESHOLD = 100   # RMS energy
SILENCE_FRAMES_TO_TRIGGER = 15   # ~1.5s of silence at 100ms chunks triggers end


# ========================== HEALTH CHECK ==========================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "asr",
        "whisper_model": MODEL_SIZE,
        "vosk_available": VOSK_AVAILABLE,
    }


# ========================== BATCH TRANSCRIPTION (Whisper) ==========================

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Batch speech-to-text using faster-whisper.
    Accepts: WAV, WebM, MP3, OGG (anything ffmpeg handles).
    Returns: { "text": "...", "duration_ms": ... }
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No audio file provided")

    suffix = os.path.splitext(file.filename)[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start = time.time()

        segments, info = whisper_model.transcribe(
            tmp_path,
            beam_size=1,
            language="en",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        text = " ".join(segment.text.strip() for segment in segments)
        elapsed_ms = int((time.time() - start) * 1000)

        print(f"[ASR-Whisper] Transcribed in {elapsed_ms}ms: '{text[:80]}'")
        return {"text": text, "duration_ms": elapsed_ms}

    except Exception as e:
        print(f"[ASR-Whisper] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


# ========================== STREAMING ASR (Vosk WebSocket) ==========================

@app.websocket("/ws/asr-stream")
async def asr_stream(websocket: WebSocket):
    """
    Real-time streaming ASR using Vosk.

    Protocol:
      Client → binary WebSocket frames: 16kHz 16-bit PCM mono audio chunks
      Server → JSON text frames:
        {"partial": "hello"}         — partial (in-progress) transcript
        {"text": "hello world"}      — final transcript after silence
        {"done": true}               — client sent close signal

    VAD: silence detected when RMS energy < threshold for N consecutive frames.
    LLM trigger: server sends final "text" event; client should forward to chat.
    """
    if not VOSK_AVAILABLE:
        await websocket.close(code=1011, reason="Vosk model not available")
        return

    await websocket.accept()

    recognizer = KaldiRecognizer(vosk_model, VOSK_SAMPLE_RATE)
    recognizer.SetWords(False)  # faster without word timestamps

    silence_count = 0
    audio_buffer = bytearray()

    print("[ASR-Vosk] Client connected for streaming ASR")

    try:
        while True:
            try:
                # Receive raw binary PCM from client
                data = await asyncio.wait_for(websocket.receive_bytes(), timeout=30.0)
            except asyncio.TimeoutError:
                print("[ASR-Vosk] Client timeout, closing")
                break
            except WebSocketDisconnect:
                break

            # Check if client sent end-of-stream signal (empty bytes)
            if len(data) == 0:
                # Flush final result
                result = json.loads(recognizer.FinalResult())
                final_text = result.get("text", "").strip()
                if final_text:
                    await websocket.send_text(json.dumps({"text": final_text}))
                await websocket.send_text(json.dumps({"done": True}))
                break

            # Energy-based VAD
            import struct
            try:
                samples = struct.unpack(f"<{len(data)//2}h", data)
                rms = (sum(s*s for s in samples) / len(samples)) ** 0.5
            except Exception:
                rms = SILENCE_ENERGY_THRESHOLD + 1

            if rms < SILENCE_ENERGY_THRESHOLD:
                silence_count += 1
            else:
                silence_count = 0

            # Feed audio to Vosk
            if recognizer.AcceptWaveform(bytes(data)):
                result = json.loads(recognizer.Result())
                final_text = result.get("text", "").strip()
                if final_text:
                    print(f"[ASR-Vosk] Final: '{final_text}'")
                    await websocket.send_text(json.dumps({"text": final_text}))
                    silence_count = 0
            else:
                partial = json.loads(recognizer.PartialResult())
                partial_text = partial.get("partial", "").strip()
                if partial_text:
                    await websocket.send_text(json.dumps({"partial": partial_text}))

            # Silence-triggered flush
            if silence_count >= SILENCE_FRAMES_TO_TRIGGER:
                result = json.loads(recognizer.FinalResult())
                final_text = result.get("text", "").strip()
                if final_text:
                    print(f"[ASR-Vosk] Silence-triggered final: '{final_text}'")
                    await websocket.send_text(json.dumps({"text": final_text}))
                recognizer = KaldiRecognizer(vosk_model, VOSK_SAMPLE_RATE)  # reset
                silence_count = 0

    except Exception as e:
        print(f"[ASR-Vosk] Error: {e}")
    finally:
        print("[ASR-Vosk] Client disconnected")
        try:
            await websocket.close()
        except Exception:
            pass
