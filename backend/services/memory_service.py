# --------------------------------------------------------------------------
# backend/services/memory_service.py — HTTP client wrapper for Memory service
#
# Forwards memory operations to the Memory Docker container.
# Handles session creation, turn storage, and context retrieval.
# --------------------------------------------------------------------------

import httpx
import os

MEMORY_URL = os.getenv("MEMORY_URL", "http://memory:8002")


async def get_session_context(session_id: str) -> dict:
    """Retrieve conversation history and patient profile for a session."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{MEMORY_URL}/session/{session_id}/context")
        return response.json()


async def add_turn(session_id: str, role: str, content: str) -> dict:
    """Save a conversation turn (user or assistant) to memory."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{MEMORY_URL}/session/add-turn", json={
            "session_id": session_id,
            "role": role,
            "content": content,
        })
        return response.json()


async def create_session(session_id: str, patient_id: str = None) -> dict:
    """Create a new session, optionally linked to a patient."""
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {"session_id": session_id}
        if patient_id:
            payload["patient_id"] = patient_id
        response = await client.post(f"{MEMORY_URL}/session/create", json=payload)
        return response.json()
