# --------------------------------------------------------------------------
# backend/main.py — Unified FastAPI backend entry point
#
# Consolidates gateway + voice routes into a single deployable backend.
# This is the entry point for Render deployment and can also run locally.
# Mounts: chat routes (existing) + voice routes (new).
# --------------------------------------------------------------------------

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.chat import router as chat_router
from routes.voice import router as voice_router

app = FastAPI(
    title="Doctor Chatbot — Backend API",
    description="Unified backend with chat and voice pipeline endpoints",
    version="2.0.0",
)

# ---------------------------------------------------------------------------
# CORS — allow all origins for development and Vercel frontend
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Transcribed-Text",
        "X-Response-Text",
        "X-Total-Time-Ms",
        "X-Synthesis-Time-Ms",
    ],
)

# ---------------------------------------------------------------------------
# Mount route modules
# ---------------------------------------------------------------------------
app.include_router(chat_router)
app.include_router(voice_router)


@app.get("/")
async def root():
    return {
        "service": "doctor-chatbot-backend",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "chat": "/ws/chat/{session_id}",
            "voice_transcribe": "/api/voice/transcribe",
            "voice_synthesize": "/api/voice/synthesize",
            "voice_chat": "/api/voice/chat",
        },
    }
