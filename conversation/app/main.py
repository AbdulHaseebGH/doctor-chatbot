# conversation/app/main.py
# --------------------------------------------------------------------------
# Conversation Manager — Phase 3+4 Upgrade
#
# Orchestrates the full pipeline per request:
#   1. Fetch session context from memory
#   2. Classify intent (knowledge / action / general) [Phase 3]
#   3. Parallel: RAG retrieval + patient search [Phase 4]
#   4. Build structured prompt (system + RAG + tools + history + query)
#   5. Stream LLM response
#   6. If tool call detected → execute → re-inject → second LLM call [Phase 2]
#   7. Save turns, extract patient info
#   8. Latency logging [Phase 4]
# --------------------------------------------------------------------------

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx, json, asyncio, re, time

app = FastAPI(title="Conversation Service")

MEMORY_URL = "http://memory:8002"
LLM_URL = "http://llm:8003"

# ---------------------------------------------------------------------------
# Module-level startup: build RAG index + import tools
# ---------------------------------------------------------------------------
from prompts import build_messages
from rag.vector_store import build_index
from rag.retriever import retrieve_formatted
from tools.orchestrator import parse_tool_call, execute_tool, format_tool_result
from cache import response_cache

# Build FAISS index from documents folder at startup
build_index()

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str
    message: str
    patient_id: str = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "conversation"}


# ---------------------------------------------------------------------------
# Intent Classification [Phase 3]
# ---------------------------------------------------------------------------

# Keywords that suggest a knowledge/information query → use RAG
KNOWLEDGE_KEYWORDS = [
    "hours", "open", "close", "when", "where", "location", "address", "phone",
    "doctor", "specialist", "pediatric", "cardio", "general", "available",
    "what", "how", "procedure", "test", "x-ray", "ecg", "blood test", "vaccine",
    "cost", "price", "insurance", "payment", "policy", "cancel", "refill",
    "prescription", "parking", "bus", "walk-in",
]

# Keywords that suggest an action is needed → use tools
ACTION_KEYWORDS = [
    "book", "schedule", "appointment", "reserve", "cancel appointment",
    "my appointment", "show appointment", "list appointment",
    "register", "create patient", "update", "add patient",
    "calculate", "how much is", "what is", "compute",
]

def classify_intent(message: str) -> str:
    """
    Classify the user's intent:
    - "knowledge" → use RAG retrieval
    - "action"    → use tools
    - "general"   → plain LLM response

    Simple keyword matching — fast, no LLM needed for routing.
    """
    msg_lower = message.lower()

    if any(kw in msg_lower for kw in ACTION_KEYWORDS):
        return "action"

    if any(kw in msg_lower for kw in KNOWLEDGE_KEYWORDS):
        return "knowledge"

    return "general"


# ---------------------------------------------------------------------------
# Main chat endpoint
# ---------------------------------------------------------------------------

@app.post("/chat")
async def chat(request: ChatRequest):
    client = httpx.AsyncClient(timeout=120)
    t_start = time.time()

    # 1. Intent classification [Phase 3]
    intent = classify_intent(request.message)
    print(f"[CONVERSATION] Intent: {intent} | Query: '{request.message[:60]}'")

    # 2. Parallel fetch: session context + RAG retrieval [Phase 4]
    async def fetch_context():
        r = await client.get(f"{MEMORY_URL}/session/{request.session_id}/context")
        return r.json()

    async def fetch_rag():
        """Only run RAG for knowledge and action intents."""
        if intent in ("knowledge", "action"):
            return retrieve_formatted(request.message, k=3)
        return ""

    context, retrieved_docs = await asyncio.gather(fetch_context(), fetch_rag())
    t_retrieval = time.time()

    history = context.get("history", [])
    patient_profile = context.get("patient_profile")

    # 3. Try to find patient if not already linked (existing logic)
    if not patient_profile:
        phone_match = re.search(r"[\d\-]{10,}", request.message)
        if phone_match:
            try:
                search_resp = await client.get(
                    f"{MEMORY_URL}/patient/search",
                    params={"phone": phone_match.group()}
                )
                result = search_resp.json()
                if result.get("found"):
                    patient_profile = result["profile"]
                    await client.post(f"{MEMORY_URL}/session/create", json={
                        "session_id": request.session_id,
                        "patient_id": result["patient_id"]
                    })
                    print(f"[CONVERSATION] Returning patient loaded: {result['patient_id']}")
            except Exception as e:
                print(f"[CONVERSATION] Patient search failed: {e}")

    # 4. Save user turn to memory
    await client.post(f"{MEMORY_URL}/session/add-turn", json={
        "session_id": request.session_id,
        "role": "user",
        "content": request.message
    })

    print(f"[LATENCY] Retrieval: {int((t_retrieval - t_start)*1000)}ms")

    # 5. Build initial messages (no tool results yet)
    messages = build_messages(
        history,
        request.message,
        patient_profile,
        retrieved_docs=retrieved_docs,
        tool_results=None,
    )

    # ---------------------------------------------------------------------------
    # Streaming generator — handles tool call detection and re-LLM flow
    # ---------------------------------------------------------------------------
    async def stream_response():
        nonlocal messages
        full_response = ""
        t_llm_start = time.time()
        first_token_sent = False

        try:
            # --- First LLM call ---
            async with client.stream(
                "POST",
                f"{LLM_URL}/generate",
                json={"messages": messages, "stream": True}
            ) as llm_resp:
                async for line in llm_resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            token = data.get("token", "")
                            full_response += token
                            # Hide tool JSON from user by buffering "action" intents during pass 1
                            if intent != "action":
                                if not first_token_sent and token.strip():
                                    t_ttft = int((time.time() - t_llm_start) * 1000)
                                    print(f"[LATENCY] TTFT: {t_ttft}ms")
                                    first_token_sent = True
                                yield f"data: {json.dumps({'token': token})}\n\n"
                        except Exception:
                            continue

            # --- Check for tool call in response [Phase 2] ---
            tool_call, raw_tool_json = parse_tool_call(full_response)

            if tool_call and intent == "action":
                t_tool_start = time.time()
                print(f"[TOOL] Tool call detected: {tool_call}")

                # Execute tool
                tool_result = await execute_tool(tool_call)
                tool_result_text = format_tool_result(tool_call, tool_result)
                t_tool_end = time.time()
                print(f"[LATENCY] Tool exec: {int((t_tool_end - t_tool_start)*1000)}ms | Result: {tool_result}")

                # Build second-pass messages with tool results
                messages2 = build_messages(
                    history,
                    request.message,
                    patient_profile,
                    retrieved_docs=retrieved_docs,
                    tool_results=tool_result_text,
                )
                # Strip the tool call JSON from the first response before saving
                clean_response = full_response.replace(raw_tool_json, "").strip()

                # Second LLM call — respond using tool result
                second_response = ""
                async with client.stream(
                    "POST",
                    f"{LLM_URL}/generate",
                    json={"messages": messages2, "stream": True}
                ) as llm_resp2:
                    async for line in llm_resp2.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                token = data.get("token", "")
                                second_response += token
                                if not first_token_sent and token.strip():
                                    t_ttft = int((time.time() - t_llm_start) * 1000)
                                    print(f"[LATENCY] TTFT (Pass 2): {t_ttft}ms")
                                    first_token_sent = True
                                yield f"data: {json.dumps({'token': token})}\n\n"
                            except Exception:
                                continue

                # Use second response as final
                full_response = second_response if second_response else clean_response
            
            elif intent == "action":
                # Action intent but NO tool call was made. Since we buffered it, we must flush it now.
                clean_response = full_response.replace(raw_tool_json, "").strip() if raw_tool_json else full_response.strip()
                if clean_response:
                    yield f"data: {json.dumps({'token': clean_response})}\n\n"
                full_response = clean_response

            # --- Save assistant turn ---
            await client.post(f"{MEMORY_URL}/session/add-turn", json={
                "session_id": request.session_id,
                "role": "assistant",
                "content": full_response
            })

            # --- Extract patient info async ---
            asyncio.create_task(
                extract_and_save_patient(
                    client,
                    request.session_id,
                    f"User: {request.message}\nAssistant: {full_response}"
                )
            )

            t_total = int((time.time() - t_start) * 1000)
            print(f"[LATENCY] Total: {t_total}ms | Intent: {intent}")

            yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"

        finally:
            await client.aclose()

    return StreamingResponse(stream_response(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Session endpoints (proxy to memory)
# ---------------------------------------------------------------------------

@app.post("/session/create")
async def create_session(data: dict):
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {k: v for k, v in data.items() if v is not None}
        payload["session_id"] = data["session_id"]
        response = await client.post(f"{MEMORY_URL}/session/create", json=payload)
        return response.json()


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.delete(f"{MEMORY_URL}/session/{session_id}")
        return response.json()


# ---------------------------------------------------------------------------
# Patient info extractor (unchanged logic, now as background task)
# ---------------------------------------------------------------------------

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
        # Use a fresh client for background task
        async with httpx.AsyncClient(timeout=30) as bg_client:
            resp = await bg_client.post(
                f"{LLM_URL}/generate",
                json={"messages": extract_prompt, "stream": False}
            )
            result = resp.json()
            content = result.get("content", "").strip()
            content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)

            if not any(v for v in data.values() if v):
                return

            search_params = {}
            if data.get("name"):
                search_params["name"] = data["name"]
            if data.get("phone"):
                search_params["phone"] = data["phone"]

            search_resp = await bg_client.get(
                f"{MEMORY_URL}/patient/search",
                params=search_params
            )
            search_result = search_resp.json()

            if search_result.get("found"):
                patient_id = search_result["patient_id"]
            else:
                patient_id = session_id[:8]

            await bg_client.post(f"{MEMORY_URL}/patient/update", json={
                "patient_id": patient_id,
                **{k: v for k, v in data.items() if v}
            })
            await bg_client.post(f"{MEMORY_URL}/session/create", json={
                "session_id": session_id,
                "patient_id": patient_id
            })
            print(f"[CONVERSATION] Patient saved: {data}")

    except Exception as e:
        print(f"[CONVERSATION] Extraction failed: {e}")