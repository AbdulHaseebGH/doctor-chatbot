# --------------------------------------------------------------------------
# asr/app/main.py — Speech-to-Text Service using faster-whisper
#
# Provides a single POST /transcribe endpoint that accepts audio files
# (WAV, WebM, MP3, OGG) and returns transcribed text using the faster-whisper
# library with int8 quantisation for fast CPU inference.
#
# Model: whisper "base" (~140 MB) — good balance of speed vs accuracy.
# Target: <500ms transcription for a 5-second clip on CPU.
# --------------------------------------------------------------------------

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import tempfile, os, time

app = FastAPI(title="ASR Service — faster-whisper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Load the model once at startup so every request is fast.
# compute_type="int8" gives ~2x speedup on CPU vs float32.
# ---------------------------------------------------------------------------
from faster_whisper import WhisperModel

MODEL_SIZE = os.getenv("MODEL_SIZE", "base")
model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
print(f"[ASR] Loaded faster-whisper model: {MODEL_SIZE} (int8, CPU)")


@app.get("/health")
async def health():
    """Health check — confirms service and model are ready."""
    return {"status": "ok", "service": "asr", "model": MODEL_SIZE}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Accept an audio file and return transcribed text.

    Supported formats: WAV, WebM, MP3, OGG, FLAC (anything ffmpeg can decode).
    Returns: { "text": "...", "duration_ms": ... }
    """
    # Validate file was provided
    if not file.filename:
        raise HTTPException(status_code=400, detail="No audio file provided")

    # Save uploaded audio to a temp file (faster-whisper needs a file path)
    suffix = os.path.splitext(file.filename)[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start = time.time()

        # Transcribe — beam_size=1 is fastest, good enough for real-time voice
        segments, info = model.transcribe(
            tmp_path,
            beam_size=1,
            language="en",
            vad_filter=True,          # Skip silent segments for speed
            vad_parameters=dict(
                min_silence_duration_ms=500,
            ),
        )

        # Collect all segment texts
        text = " ".join(segment.text.strip() for segment in segments)
        elapsed_ms = int((time.time() - start) * 1000)

        print(f"[ASR] Transcribed in {elapsed_ms}ms: '{text[:80]}...'")
        return {"text": text, "duration_ms": elapsed_ms}

    except Exception as e:
        print(f"[ASR] Transcription error: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    finally:
        # Clean up temp file
        os.unlink(tmp_path)
