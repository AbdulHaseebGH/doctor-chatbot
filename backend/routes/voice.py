# --------------------------------------------------------------------------
# backend/routes/voice.py — Voice pipeline API routes
#
# Three endpoints for the voice agent:
# 1. POST /api/voice/transcribe — audio → text (ASR only)
# 2. POST /api/voice/synthesize — text → audio (TTS only)
# 3. POST /api/voice/chat — full pipeline: audio → text → LLM → audio
#
# Concurrency is limited to 4 simultaneous voice sessions via asyncio
# semaphore. Returns 503 if capacity is exceeded.
# --------------------------------------------------------------------------

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import io
import time

from services.asr_service import transcribe_audio
from services.tts_service import synthesize_speech
from services.llm_service import generate_response
from services.memory_service import get_session_context, add_turn

router = APIRouter(prefix="/api/voice", tags=["voice"])

# ---------------------------------------------------------------------------
# Concurrency limiter — max 4 simultaneous voice sessions.
# Uses asyncio.Semaphore to queue requests; if all slots are taken and the
# caller doesn't want to wait, we return 503 immediately.
# ---------------------------------------------------------------------------
MAX_CONCURRENT_VOICE = 4
voice_semaphore = asyncio.Semaphore(MAX_CONCURRENT_VOICE)
active_sessions = 0


class SynthesizeRequest(BaseModel):
    text: str


@router.post("/transcribe")
async def voice_transcribe(file: UploadFile = File(...)):
    """
    Speech-to-Text endpoint.
    Accepts audio file (WAV, WebM, MP3), returns transcribed text.

    Returns: { "text": "...", "duration_ms": ... }
    """
    global active_sessions

    # Check capacity before acquiring semaphore
    if active_sessions >= MAX_CONCURRENT_VOICE:
        raise HTTPException(
            status_code=503,
            detail=f"Voice service at capacity ({MAX_CONCURRENT_VOICE} concurrent sessions). "
                   f"Please try again in a few seconds."
        )

    try:
        async with voice_semaphore:
            active_sessions += 1
            try:
                audio_bytes = await file.read()
                result = await transcribe_audio(audio_bytes, file.filename or "audio.webm")
                return result
            finally:
                active_sessions -= 1
    except HTTPException:
        raise
    except Exception as e:
        active_sessions = max(0, active_sessions - 1)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.post("/synthesize")
async def voice_synthesize(request: SynthesizeRequest):
    """
    Text-to-Speech endpoint.
    Accepts text, returns streaming WAV audio.

    Accepts: { "text": "Hello, how can I help you?" }
    Returns: audio/wav stream
    """
    global active_sessions

    if active_sessions >= MAX_CONCURRENT_VOICE:
        raise HTTPException(
            status_code=503,
            detail=f"Voice service at capacity ({MAX_CONCURRENT_VOICE} concurrent sessions). "
                   f"Please try again in a few seconds."
        )

    try:
        async with voice_semaphore:
            active_sessions += 1
            try:
                audio_bytes = await synthesize_speech(request.text)
                return StreamingResponse(
                    io.BytesIO(audio_bytes),
                    media_type="audio/wav",
                    headers={"Content-Disposition": "inline; filename=speech.wav"},
                )
            finally:
                active_sessions -= 1
    except HTTPException:
        raise
    except Exception as e:
        active_sessions = max(0, active_sessions - 1)
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")


@router.post("/chat")
async def voice_chat(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):
    """
    Full voice pipeline endpoint: audio in → text → LLM → audio out.
    Combines ASR, LLM inference, and TTS in a single request for lowest latency.

    Accepts: multipart form with audio file + session_id
    Returns: WAV audio stream of the AI response

    Also returns headers:
    - X-Transcribed-Text: what the user said
    - X-Response-Text: what the AI responded
    - X-Total-Time-Ms: total pipeline time
    """
    global active_sessions

    if active_sessions >= MAX_CONCURRENT_VOICE:
        raise HTTPException(
            status_code=503,
            detail=f"Voice service at capacity ({MAX_CONCURRENT_VOICE} concurrent sessions). "
                   f"Please try again in a few seconds."
        )

    try:
        async with voice_semaphore:
            active_sessions += 1
            try:
                pipeline_start = time.time()

                # Step 1: ASR — convert audio to text
                audio_bytes = await file.read()
                asr_result = await transcribe_audio(audio_bytes, file.filename or "audio.webm")
                user_text = asr_result.get("text", "").strip()

                if not user_text:
                    raise HTTPException(status_code=400, detail="Could not transcribe any speech from the audio")

                # Step 2: Get context from memory and build LLM messages
                context = await get_session_context(session_id)
                history = context.get("history", [])
                patient_profile = context.get("patient_profile")

                # Build messages using the same prompt format as the conversation service
                from prompts import build_messages
                messages = build_messages(history, user_text, patient_profile)

                # Save user turn to memory
                await add_turn(session_id, "user", user_text)

                # Step 3: LLM — generate response (non-streaming for voice pipeline)
                # Use lower max_tokens (150) for voice to keep responses short and fast
                llm_response = await generate_response(
                    messages, stream=False, max_tokens=150, temperature=0.7
                )

                # Save assistant turn to memory
                await add_turn(session_id, "assistant", llm_response)

                # Step 4: TTS — convert response to audio
                audio_response = await synthesize_speech(llm_response)

                total_ms = int((time.time() - pipeline_start) * 1000)
                print(f"[VOICE] Full pipeline: {total_ms}ms | "
                      f"User: '{user_text[:50]}' | AI: '{llm_response[:50]}'")

                return StreamingResponse(
                    io.BytesIO(audio_response),
                    media_type="audio/wav",
                    headers={
                        "Content-Disposition": "inline; filename=response.wav",
                        "X-Transcribed-Text": user_text[:200],
                        "X-Response-Text": llm_response[:200],
                        "X-Total-Time-Ms": str(total_ms),
                    },
                )
            finally:
                active_sessions -= 1
    except HTTPException:
        raise
    except Exception as e:
        active_sessions = max(0, active_sessions - 1)
        raise HTTPException(status_code=500, detail=f"Voice pipeline error: {str(e)}")
