# conversation/app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx, json

app = FastAPI(title="Conversation Service")

MEMORY_URL = "http://memory:8002"
LLM_URL = "http://llm:8003"

from prompts import build_messages

class ChatRequest(BaseModel):
    session_id: str
    message: str
    patient_id: str = None

@app.get("/health")
async def health():
    return {"status": "ok", "service": "conversation"}

@app.post("/chat")
async def chat(request: ChatRequest):
    client = httpx.AsyncClient(timeout=120)

    # 1. Get context from memory
    ctx_response = await client.get(f"{MEMORY_URL}/session/{request.session_id}/context")
    context = ctx_response.json()
    history = context.get("history", [])
    patient_profile = context.get("patient_profile")

    # 2. If no patient linked yet, try to find from current message
    if not patient_profile:
        search_params = {}
        # Extract name/phone from current message quickly
        words = request.message.lower().split()
        # Check if phone number pattern exists
        import re
        phone_match = re.search(r'[\d\-]{10,}', request.message)
        if phone_match:
            search_params["phone"] = phone_match.group()
        
        if search_params:
            search_resp = await client.get(
                f"{MEMORY_URL}/patient/search",
                params=search_params
            )
            search_result = search_resp.json()
            if search_result.get("found"):
                patient_profile = search_result["profile"]
                # Link session to found patient immediately
                await client.post(f"{MEMORY_URL}/session/create", json={
                    "session_id": request.session_id,
                    "patient_id": search_result["patient_id"]
                })
                print(f"[CONVERSATION] Returning patient loaded: {search_result['patient_id']}")

    # 3. Build messages for LLM
    messages = build_messages(history, request.message, patient_profile)
    # rest of function stays the same...
    
    # 3. Save user turn to memory
    save_resp = await client.post(f"{MEMORY_URL}/session/add-turn", json={
        "session_id": request.session_id,
        "role": "user",
        "content": request.message
    })
    print(f"[MEMORY] Save user turn: {save_resp.status_code} {save_resp.text}")

    async def stream_response():
        full_response = ""
        try:
            async with client.stream("POST", f"{LLM_URL}/generate",
                                     json={"messages": messages, "stream": True}) as llm_resp:
                async for line in llm_resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            token = data.get("token", "")
                            full_response += token
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        except:
                            continue

            save_resp2 = await client.post(f"{MEMORY_URL}/session/add-turn", json={
                "session_id": request.session_id,
                "role": "assistant",
                "content": full_response
            })
            print(f"[MEMORY] Save assistant turn: {save_resp2.status_code} {save_resp2.text}")
            
            await extract_and_save_patient(client, request.session_id, 
            f"User: {request.message}\nAssistant: {full_response}")
            
            yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"
        finally:
            await client.aclose()

    return StreamingResponse(stream_response(), media_type="text/event-stream")

@app.post("/session/create")
async def create_session(data: dict):
    async with httpx.AsyncClient(timeout=30) as client:
        # Clean None values
        payload = {k: v for k, v in data.items() if v is not None}
        payload["session_id"] = data["session_id"]
        response = await client.post(f"{MEMORY_URL}/session/create", json=payload)
        return response.json()
    

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.delete(f"{MEMORY_URL}/session/{session_id}")
        return response.json()


# After saving assistant turn, extract patient info
async def extract_and_save_patient(client, session_id, full_conversation):
    extract_prompt = [
        {
            "role": "system",
            "content": """Extract patient information from this conversation. 
Return ONLY a JSON object with these fields (use null if not mentioned):
{"name": null, "age": null, "phone": null, "symptom": null}
Return ONLY the JSON, nothing else. No explanation."""
        },
        {
            "role": "user",
            "content": f"Conversation: {full_conversation}"
        }
    ]

    try:
        resp = await client.post(f"{LLM_URL}/generate",
                                 json={"messages": extract_prompt, "stream": False})
        result = resp.json()
        content = result.get("content", "").strip()
        content = content.replace("```json", "").replace("```", "").strip()
        data = json.loads(content)

        if not any(v for v in data.values() if v):
            print("[CONVERSATION] No patient info found")
            return

        # Search for existing patient by name + phone
        search_params = {}
        if data.get("name"):
            search_params["name"] = data["name"]
        if data.get("phone"):
            search_params["phone"] = data["phone"]

        search_resp = await client.get(
            f"{MEMORY_URL}/patient/search",
            params=search_params
        )
        search_result = search_resp.json()

        if search_result.get("found"):
            # Returning patient — use existing ID
            patient_id = search_result["patient_id"]
            print(f"[CONVERSATION] Returning patient found: {patient_id}")
        else:
            # New patient — use session prefix as ID
            patient_id = session_id[:8]
            print(f"[CONVERSATION] New patient created: {patient_id}")

        # Save/update patient profile
        await client.post(f"{MEMORY_URL}/patient/update", json={
            "patient_id": patient_id,
            **{k: v for k, v in data.items() if v}
        })

        # Link session to patient
        await client.post(f"{MEMORY_URL}/session/create", json={
            "session_id": session_id,
            "patient_id": patient_id
        })
        print(f"[CONVERSATION] Patient saved: {data}")

    except Exception as e:
        print(f"[CONVERSATION] Extraction failed: {e}")