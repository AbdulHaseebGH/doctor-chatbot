# --------------------------------------------------------------------------
# backend/routes/chat.py — Chat API routes (migrated from gateway)
#
# These routes handle the existing chat functionality:
# - POST /session — create new chat session
# - DELETE /session/{id} — delete a session
# - GET /patient/{id} — get patient profile
# - WebSocket /ws/chat/{id} — streaming chat
# --------------------------------------------------------------------------

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import httpx
import json
import uuid
import os

router = APIRouter(tags=["chat"])

CONVERSATION_URL = os.getenv("CONVERSATION_URL", "http://conversation:8001")
MEMORY_URL = os.getenv("MEMORY_URL", "http://memory:8002")


class SessionRequest(BaseModel):
    patient_id: str = None


@router.get("/health")
async def health():
    return {"status": "ok", "service": "backend"}


@router.post("/session")
async def create_session(data: SessionRequest):
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r1 = await client.post(f"{CONVERSATION_URL}/session/create", json={
                "session_id": session_id,
                "patient_id": data.patient_id,
            })
            print(f"[BACKEND] Conversation create: {r1.status_code}")
        except Exception as e:
            print(f"[BACKEND] Conversation ERROR: {e}")

        try:
            r2 = await client.post(f"{MEMORY_URL}/session/create", json={
                "session_id": session_id,
                "patient_id": data.patient_id,
            })
            print(f"[BACKEND] Memory create: {r2.status_code}")
        except Exception as e:
            print(f"[BACKEND] Memory ERROR: {e}")

    return {"session_id": session_id}


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{CONVERSATION_URL}/session/{session_id}")
    return {"status": "deleted"}


@router.get("/patient/{patient_id}")
async def get_patient(patient_id: str):
    """Get patient profile by ID."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{MEMORY_URL}/patient/{patient_id}")
        return response.json()


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for streaming chat — proxies to conversation service."""
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
                    json={"session_id": session_id, "message": user_message},
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
        print(f"[BACKEND] WebSocket error: {e}")
        await websocket.close()
