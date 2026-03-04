# llm/app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import json

app = FastAPI(title="LLM Service")

LM_STUDIO_URL = "http://host.docker.internal:1234/v1/chat/completions"
MODEL_NAME = "qwen2.5-3b-instruct-q4_k_m"

class LLMRequest(BaseModel):
    messages: list
    stream: bool = True
    max_tokens: int = 300
    temperature: float = 0.7

@app.get("/health")
async def health():
    return {"status": "ok", "service": "llm"}

@app.post("/generate")
async def generate(request: LLMRequest):
    payload = {
        "model": MODEL_NAME,
        "messages": request.messages,
        "stream": request.stream,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature
    }

    if request.stream:
        async def stream_tokens():
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", LM_STUDIO_URL, json=payload) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                token = chunk["choices"][0]["delta"].get("content", "")
                                if token:
                                    yield f"data: {json.dumps({'token': token})}\n\n"
                            except json.JSONDecodeError:
                                continue
        return StreamingResponse(stream_tokens(), media_type="text/event-stream")

    else:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(LM_STUDIO_URL, json=payload)
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail="LLM inference failed")
            result = response.json()
            return {"content": result["choices"][0]["message"]["content"]}