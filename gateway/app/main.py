# gateway/app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx, json, uuid

app = FastAPI(title="API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CONVERSATION_URL = "http://conversation:8001"
MEMORY_URL = "http://memory:8002"

class SessionRequest(BaseModel):
    patient_id: str = None

@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}

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

@app.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            # Receive message from frontend
            data = await websocket.receive_text()
            payload = json.loads(data)
            user_message = payload.get("message", "")

            if not user_message.strip():
                continue

            # Stream response from conversation service
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