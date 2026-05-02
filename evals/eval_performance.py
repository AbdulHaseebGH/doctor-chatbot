"""
evals/eval_performance.py
-------------------------
Performance evaluation:
  - TTFT (Time To First Token) via WebSocket chat
  - End-to-end latency (full response)
  - Throughput (requests/sec estimate)
  - Health check latency for all services
Requires: Docker services running on localhost
"""

import asyncio
import json
import time
import httpx
import statistics

GATEWAY_URL = "http://localhost:8000"
SERVICE_URLS = {
    "gateway":      "http://localhost:8000/health",
    "conversation": "http://localhost:8001/health",
    "memory":       "http://localhost:8002/health",
    "llm":          "http://localhost:8003/health",
    "asr":          "http://localhost:8004/health",
    "tts":          "http://localhost:8005/health",
}

TEST_MESSAGES = [
    "What are your clinic hours?",
    "When is Dr. Khan available?",
    "I'd like to book an appointment",
    "Do you accept insurance?",
]


async def health_check_all() -> dict:
    """Measure health check latency for each service."""
    print("\n[PERF] Service health checks")
    results = {}
    async with httpx.AsyncClient(timeout=10) as client:
        for name, url in SERVICE_URLS.items():
            try:
                t0 = time.time()
                resp = await client.get(url)
                latency_ms = int((time.time() - t0) * 1000)
                status = "✅ UP" if resp.status_code == 200 else f"⚠️ {resp.status_code}"
                print(f"  {name:15s}: {status} ({latency_ms}ms)")
                results[name] = {"status": resp.status_code, "latency_ms": latency_ms}
            except Exception as e:
                print(f"  {name:15s}: ❌ DOWN ({e})")
                results[name] = {"status": "error", "error": str(e)}
    return results


async def measure_chat_latency(session_id: str, message: str) -> dict:
    """Measure TTFT and total latency for a chat message."""
    import websockets

    ws_url = f"ws://localhost:8000/ws/chat/{session_id}"
    t_start = time.time()
    t_first_token = None
    full_response = ""

    try:
        async with websockets.connect(ws_url, ping_timeout=None) as ws:
            await ws.send(json.dumps({"message": message}))

            async for raw in ws:
                data = json.loads(raw)
                token = data.get("token", "")
                if token.strip() and t_first_token is None:
                    t_first_token = time.time()
                full_response += token
                if data.get("done"):
                    break
    except Exception as e:
        return {"error": str(e), "message": message}

    t_end = time.time()
    ttft_ms = int((t_first_token - t_start) * 1000) if t_first_token else None
    total_ms = int((t_end - t_start) * 1000)

    return {
        "message": message,
        "ttft_ms": ttft_ms,
        "total_ms": total_ms,
        "response_length": len(full_response),
        "tokens_approx": len(full_response.split()),
    }


async def run_latency_benchmark(n_runs: int = 4) -> dict:
    """Run N chat messages and collect latency statistics."""
    print(f"\n[PERF] Latency benchmark — {n_runs} messages")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{GATEWAY_URL}/session", json={})
        session_id = resp.json()["session_id"]

    results = []
    for i, msg in enumerate(TEST_MESSAGES[:n_runs]):
        print(f"  [{i+1}/{n_runs}] '{msg[:50]}'")
        r = await measure_chat_latency(session_id, msg)
        if "error" not in r:
            print(f"    TTFT: {r['ttft_ms']}ms | Total: {r['total_ms']}ms | Words: {r['tokens_approx']}")
        else:
            print(f"    ERROR: {r['error']}")
        results.append(r)
        await asyncio.sleep(0.5)

    valid = [r for r in results if "error" not in r]
    if not valid:
        return {"error": "No successful measurements"}

    ttfts = [r["ttft_ms"] for r in valid if r["ttft_ms"]]
    totals = [r["total_ms"] for r in valid]

    stats = {
        "runs": len(valid),
        "ttft_ms": {
            "min": min(ttfts) if ttfts else None,
            "max": max(ttfts) if ttfts else None,
            "mean": round(statistics.mean(ttfts), 1) if ttfts else None,
        },
        "total_ms": {
            "min": min(totals),
            "max": max(totals),
            "mean": round(statistics.mean(totals), 1),
        },
        "target_met": {
            "preprocessing_under_2s": all(
                (r.get("ttft_ms") or 9999) < 2000 for r in valid
            ),
        },
    }

    print(f"\n  TTFT:  mean={stats['ttft_ms']['mean']}ms | min={stats['ttft_ms']['min']}ms | max={stats['ttft_ms']['max']}ms")
    print(f"  Total: mean={stats['total_ms']['mean']}ms | min={stats['total_ms']['min']}ms | max={stats['total_ms']['max']}ms")
    print(f"  Pre-processing <2s target: {'✅ MET' if stats['target_met']['preprocessing_under_2s'] else '❌ NOT MET'}")

    return {"benchmark": stats, "details": results}


async def run_performance_eval() -> dict:
    print(f"\n{'='*60}")
    print("PERFORMANCE EVALUATION")
    print(f"{'='*60}")

    health = await health_check_all()
    latency = await run_latency_benchmark()

    return {
        "health_checks": health,
        "latency_benchmark": latency,
    }


if __name__ == "__main__":
    asyncio.run(run_performance_eval())
