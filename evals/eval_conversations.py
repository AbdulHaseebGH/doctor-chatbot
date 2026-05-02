"""
evals/eval_conversations.py
---------------------------
Conversational evaluation: replays test dialogues against the live system
and scores each conversation on:
  - task_completion: did response contain required keywords?
  - coherence: response length > 10 words (heuristic)
  - policy_adherence: off-topic rejected, no medical advice given
"""

import asyncio
import json
import httpx
import time
import uuid
from pathlib import Path

GATEWAY_URL = "http://localhost:8000"
CONVERSATIONS_FILE = Path(__file__).parent / "test_conversations.json"
TIMEOUT = 120


async def create_session() -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{GATEWAY_URL}/session", json={})
        return resp.json()["session_id"]


async def send_message(session_id: str, message: str) -> str:
    """Send a message via WebSocket chat and collect the full response."""
    import websockets

    ws_url = f"ws://localhost:8000/ws/chat/{session_id}"
    full_response = ""

    try:
        async with websockets.connect(ws_url, ping_timeout=None) as ws:
            await ws.send(json.dumps({"message": message}))
            async for raw in ws:
                data = json.loads(raw)
                token = data.get("token", "")
                full_response += token
                if data.get("done"):
                    break
    except Exception as e:
        full_response = f"[ERROR: {e}]"

    return full_response


def score_response(response: str, expected: dict) -> dict:
    """Score a single response against expected outcomes."""
    response_lower = response.lower()
    scores = {}

    # Task completion: required keywords present
    required = expected.get("required_keywords", [])
    if required:
        found = [kw for kw in required if kw.lower() in response_lower]
        scores["task_completion"] = len(found) / len(required)
    else:
        scores["task_completion"] = 1.0

    # Coherence: response length > 10 words
    word_count = len(response.split())
    scores["coherence"] = 1.0 if word_count >= 10 else max(0, word_count / 10)

    # Policy: must NOT contain forbidden phrases
    forbidden = expected.get("must_not_contain", [])
    violations = [f for f in forbidden if f.lower() in response_lower]
    scores["policy_adherence"] = 1.0 if not violations else 0.0
    if violations:
        scores["policy_violations"] = violations

    return scores


async def run_conversation_eval(conversation: dict) -> dict:
    """Run a single conversation and score all turns."""
    conv_id = conversation["id"]
    description = conversation["description"]
    turns = conversation["turns"]
    expected = conversation.get("expected_outcomes", {})

    print(f"\n  [{conv_id}] {description}")

    session_id = await create_session()
    responses = []
    all_scores = []

    for i, turn in enumerate(turns):
        user_msg = turn["user"]
        print(f"    User: {user_msg[:60]}")

        t0 = time.time()
        response = await send_message(session_id, user_msg)
        latency_ms = int((time.time() - t0) * 1000)

        print(f"    Sara: {response[:80]}{'...' if len(response) > 80 else ''}")
        print(f"    Latency: {latency_ms}ms")

        responses.append({
            "turn": i + 1,
            "user": user_msg,
            "response": response,
            "latency_ms": latency_ms,
        })

        # Score last turn against expected outcomes
        if i == len(turns) - 1:
            turn_scores = score_response(response, expected)
            all_scores.append(turn_scores)

    # Aggregate scores
    avg_task = sum(s.get("task_completion", 0) for s in all_scores) / max(len(all_scores), 1)
    avg_coherence = sum(s.get("coherence", 0) for s in all_scores) / max(len(all_scores), 1)
    avg_policy = sum(s.get("policy_adherence", 0) for s in all_scores) / max(len(all_scores), 1)

    result = {
        "id": conv_id,
        "description": description,
        "scores": {
            "task_completion": round(avg_task, 2),
            "coherence": round(avg_coherence, 2),
            "policy_adherence": round(avg_policy, 2),
            "overall": round((avg_task + avg_coherence + avg_policy) / 3, 2),
        },
        "turns": responses,
    }

    print(f"    Scores → TC={avg_task:.2f} | Coh={avg_coherence:.2f} | Policy={avg_policy:.2f}")
    return result


async def run_all_conversations() -> list[dict]:
    with open(CONVERSATIONS_FILE) as f:
        conversations = json.load(f)

    print(f"\n{'='*60}")
    print(f"CONVERSATIONAL EVALUATION — {len(conversations)} dialogues")
    print(f"{'='*60}")

    results = []
    for conv in conversations:
        result = await run_conversation_eval(conv)
        results.append(result)
        await asyncio.sleep(0.5)  # small gap between sessions

    # Summary
    avg_overall = sum(r["scores"]["overall"] for r in results) / len(results)
    print(f"\n{'='*60}")
    print(f"OVERALL SCORE: {avg_overall:.2f} / 1.00")
    print(f"{'='*60}")

    return results


if __name__ == "__main__":
    results = asyncio.run(run_all_conversations())
