# gateway/app/main.py
# --------------------------------------------------------------------------
# API Gateway — routes frontend requests to backend microservices.
# Handles WebSocket chat streaming, session management, patient lookup,
# and voice pipeline proxy routes (ASR, TTS, full voice chat).
# --------------------------------------------------------------------------
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx, json, uuid, asyncio, io

app = FastAPI(title="API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Expose voice pipeline headers so frontend JS can read them
    expose_headers=[
        "X-Transcribed-Text",
        "X-Response-Text",
        "X-Total-Time-Ms",
        "X-Synthesis-Time-Ms",
    ],
)

# ---------------------------------------------------------------------------
# Service URLs — internal Docker network names
# ---------------------------------------------------------------------------
CONVERSATION_URL = "http://conversation:8001"
MEMORY_URL = "http://memory:8002"
ASR_URL = "http://asr:8004"
TTS_URL = "http://tts:8005"

# ---------------------------------------------------------------------------
# Voice concurrency limiter — max 4 simultaneous voice sessions
# ---------------------------------------------------------------------------
MAX_CONCURRENT_VOICE = 4
voice_semaphore = asyncio.Semaphore(MAX_CONCURRENT_VOICE)
active_voice_sessions = 0


class SessionRequest(BaseModel):
    patient_id: str = None


class SynthesizeRequest(BaseModel):
    text: str


# ========================== HEALTH CHECK ==========================

@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


# ========================== SESSION MANAGEMENT ==========================

@app.post("/session")
async def create_session(data: SessionRequest):
    session_id = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r1 = await client.post(f"{CONVERSATION_URL}/session/create", json={
                "session_id": session_id,
                "patient_id": data.patient_id
            })
            print(f"[GATEWAY] Conversation create: {r1.status_code} {r1.text}")
        except Exception as e:
            print(f"[GATEWAY] Conversation ERROR: {e}")

        try:
            r2 = await client.post(f"{MEMORY_URL}/session/create", json={
                "session_id": session_id,
                "patient_id": data.patient_id
            })
            print(f"[GATEWAY] Memory create: {r2.status_code} {r2.text}")
        except Exception as e:
            print(f"[GATEWAY] Memory ERROR: {e}")

    return {"session_id": session_id}


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{CONVERSATION_URL}/session/{session_id}")
    return {"status": "deleted"}


@app.get("/patient/{patient_id}")
async def get_patient(patient_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{MEMORY_URL}/patient/{patient_id}")
        return response.json()


# ========================== WEBSOCKET CHAT ==========================

@app.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            user_message = payload.get("message", "")

            if not user_message.strip():
                continue

            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{CONVERSATION_URL}/chat",
                    json={"session_id": session_id, "message": user_message}
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                chunk = json.loads(line[6:])
                                await websocket.send_text(json.dumps(chunk))
                            except:
                                continue

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.close()


# ========================== VOICE ENDPOINTS ==========================

@app.post("/api/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)):
    """
    Speech-to-Text proxy — forwards audio to ASR service.
    Returns: { "text": "...", "duration_ms": ... }
    """
    global active_voice_sessions
    if active_voice_sessions >= MAX_CONCURRENT_VOICE:
        raise HTTPException(status_code=503,
            detail=f"Voice service at capacity ({MAX_CONCURRENT_VOICE} sessions). Try again shortly.")

    async with voice_semaphore:
        active_voice_sessions += 1
        try:
            audio_bytes = await file.read()
            async with httpx.AsyncClient(timeout=30) as client:
                files = {"file": (file.filename or "audio.webm", audio_bytes)}
                resp = await client.post(f"{ASR_URL}/transcribe", files=files)
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                return resp.json()
        finally:
            active_voice_sessions -= 1


@app.post("/api/voice/synthesize")
async def voice_synthesize(request: SynthesizeRequest):
    """
    Text-to-Speech proxy — forwards text to TTS service.
    Returns: audio/wav stream
    """
    global active_voice_sessions
    if active_voice_sessions >= MAX_CONCURRENT_VOICE:
        raise HTTPException(status_code=503,
            detail=f"Voice service at capacity ({MAX_CONCURRENT_VOICE} sessions). Try again shortly.")

    async with voice_semaphore:
        active_voice_sessions += 1
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{TTS_URL}/synthesize",
                                          json={"text": request.text})
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                return StreamingResponse(
                    io.BytesIO(resp.content),
                    media_type="audio/wav",
                    headers={"Content-Disposition": "inline; filename=speech.wav"},
                )
        finally:
            active_voice_sessions -= 1


@app.post("/api/voice/chat")
async def voice_chat(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):
    """
    Full voice pipeline: audio → ASR → LLM chat → TTS → audio.
    Combines transcribe + chat + synthesize in one request for lowest latency.
    Returns: WAV audio with transcribed/response text in headers.
    """
    global active_voice_sessions
    if active_voice_sessions >= MAX_CONCURRENT_VOICE:
        raise HTTPException(status_code=503,
            detail=f"Voice service at capacity ({MAX_CONCURRENT_VOICE} sessions). Try again shortly.")

    async with voice_semaphore:
        active_voice_sessions += 1
        try:
            import time
            start = time.time()

            # Step 1: ASR
            audio_bytes = await file.read()
            async with httpx.AsyncClient(timeout=30) as client:
                files = {"file": (file.filename or "audio.webm", audio_bytes)}
                asr_resp = await client.post(f"{ASR_URL}/transcribe", files=files)
                if asr_resp.status_code != 200:
                    raise HTTPException(status_code=500, detail="ASR failed")
                user_text = asr_resp.json().get("text", "").strip()

            if not user_text:
                raise HTTPException(status_code=400, detail="No speech detected in audio")

            # Step 2: Chat via conversation service (non-streaming for voice)
            async with httpx.AsyncClient(timeout=120) as client:
                chat_resp = await client.post(f"{CONVERSATION_URL}/chat",
                    json={"session_id": session_id, "message": user_text})
                # Collect all streamed tokens
                llm_text = ""
                for line in chat_resp.text.split("\n"):
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            llm_text += data.get("token", "")
                        except:
                            continue

            if not llm_text:
                raise HTTPException(status_code=500, detail="LLM returned empty response")

            # Step 3: TTS
            async with httpx.AsyncClient(timeout=30) as client:
                tts_resp = await client.post(f"{TTS_URL}/synthesize",
                                              json={"text": llm_text})
                if tts_resp.status_code != 200:
                    raise HTTPException(status_code=500, detail="TTS failed")

            total_ms = int((time.time() - start) * 1000)
            print(f"[GATEWAY] Voice pipeline: {total_ms}ms")

            return StreamingResponse(
                io.BytesIO(tts_resp.content),
                media_type="audio/wav",
                headers={
                    "Content-Disposition": "inline; filename=response.wav",
                    "X-Transcribed-Text": user_text[:200],
                    "X-Response-Text": llm_text[:200],
                    "X-Total-Time-Ms": str(total_ms),
                },
            )
        finally:
            active_voice_sessions -= 1