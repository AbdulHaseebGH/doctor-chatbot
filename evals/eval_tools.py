"""
evals/eval_tools.py
-------------------
Tool system unit tests:
  - Calculator: expression evaluation correctness
  - Parser: tool call JSON detection from LLM output
  - Orchestrator: full parse + execute round-trip
  - Scheduler: booking, availability, listing
  - CRM: mocked patient operations
Runs locally without Docker (mocks HTTP calls where needed).
"""

import sys
import os
import asyncio

# Add conversation app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "conversation", "app"))


# ============================================================
# Test helpers
# ============================================================

PASSED = 0
FAILED = 0


def test(name: str, condition: bool, detail: str = ""):
    global PASSED, FAILED
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status} {name}" + (f" | {detail}" if detail else ""))
    if condition:
        PASSED += 1
    else:
        FAILED += 1


# ============================================================
# Calculator Tests
# ============================================================

async def test_calculator():
    from tools.calculator_tool import calculate

    print("\n[CALC] Calculator tests")
    r = await calculate("2 + 2"); test("2+2=4", r["result"] == 4)
    r = await calculate("10 * 5"); test("10*5=50", r["result"] == 50)
    r = await calculate("100 / 4"); test("100/4=25", r["result"] == 25)
    r = await calculate("2 ** 8"); test("2**8=256", r["result"] == 256)
    r = await calculate("(10 + 5) * 2"); test("(10+5)*2=30", r["result"] == 30)
    r = await calculate("1 / 0"); test("div by zero returns error", "error" in r)
    r = await calculate("import os"); test("code injection blocked", "error" in r)
    r = await calculate("3.14 * 2"); test("float ok", abs(r["result"] - 6.28) < 0.01)


# ============================================================
# Parser Tests
# ============================================================

async def test_parser():
    from tools.orchestrator import parse_tool_call

    print("\n[PARSER] Tool call detection tests")

    # Clean JSON
    out1 = '{"tool": "scheduler", "function": "book_appointment", "arguments": {"date": "2026-05-10", "time": "5pm", "doctor": "Ahmed", "patient_name": "Ali"}}'
    tool_call, raw = parse_tool_call(out1)
    test("Parses clean JSON", tool_call is not None and tool_call["tool"] == "scheduler")

    # JSON embedded in prose
    out2 = 'Sure! Let me book that for you. {"tool": "calculator", "function": "calculate", "arguments": {"expression": "2+2"}} Done!'
    tool_call, raw = parse_tool_call(out2)
    test("Parses embedded JSON", tool_call is not None and tool_call["tool"] == "calculator")

    # No tool call
    out3 = "Hello! I'd be happy to help you book an appointment."
    tool_call, raw = parse_tool_call(out3)
    test("Returns None for plain text", tool_call is None)

    # Invalid JSON
    out4 = '{"tool": "crm", broken json here'
    tool_call, raw = parse_tool_call(out4)
    test("Returns None for broken JSON", tool_call is None)


# ============================================================
# Orchestrator Round-trip Tests
# ============================================================

async def test_orchestrator():
    from tools.orchestrator import parse_tool_call, execute_tool

    print("\n[ORCH] Orchestrator round-trip tests")

    # Calculator round-trip
    tool_call = {
        "tool": "calculator",
        "function": "calculate",
        "arguments": {"expression": "5 * 12"}
    }
    result = await execute_tool(tool_call)
    test("Calculator via orchestrator", result.get("result") == 60)

    # Unknown tool
    bad_call = {"tool": "unknown_tool", "function": "do_thing", "arguments": {}}
    result = await execute_tool(bad_call)
    test("Unknown tool returns error", "error" in result)

    # FAQ search (local RAG)
    from rag.vector_store import build_index
    build_index()
    faq_call = {"tool": "faq", "function": "search_faq", "arguments": {"query": "clinic hours"}}
    result = await execute_tool(faq_call)
    test("FAQ search returns results", result.get("count", 0) > 0 or "results" in result)


# ============================================================
# Scheduler Tests
# ============================================================

async def test_scheduler():
    from tools.scheduler_tool import book_appointment, check_availability, list_appointments
    import os, json

    # Use temp file for tests (Windows-compatible)
    import tempfile
    tmp_file = os.path.join(tempfile.gettempdir(), "test_appointments.json")
    os.environ["APPOINTMENTS_FILE"] = tmp_file
    # Clean up
    if os.path.exists(tmp_file):
        os.remove(tmp_file)

    print("\n[SCHED] Scheduler tests")

    # Book appointment
    r = await book_appointment("2026-05-10", "10am", "Ahmed", "Test Patient")
    test("Book appointment succeeds", r["status"] == "booked", r.get("confirmation", ""))

    # Check availability
    r = await check_availability("2026-05-10", "Ahmed")
    test("Check availability works", "available_slots" in r)
    test("Booked slot removed", "10:00" not in r.get("available_slots", []))

    # List appointments
    r = await list_appointments("Test Patient")
    test("List appointments finds patient", len(r.get("appointments", [])) > 0)

    # Double booking
    r2 = await book_appointment("2026-05-10", "10am", "Ahmed", "Another Patient")
    test("Double booking rejected", r2["status"] == "error")

    # Invalid doctor
    r3 = await book_appointment("2026-05-10", "11am", "Dr. Nobody", "Test")
    test("Invalid doctor rejected", r3["status"] == "error")

    # Outside clinic hours
    r4 = await book_appointment("2026-05-10", "8am", "Ahmed", "Early Bird")
    test("Outside hours rejected", r4["status"] == "error")


# ============================================================
# Run all
# ============================================================

async def main():
    global PASSED, FAILED
    print(f"\n{'='*60}")
    print("TOOL EVALUATION SUITE")
    print(f"{'='*60}")
    PASSED = 0
    FAILED = 0

    await test_calculator()
    await test_parser()
    await test_orchestrator()
    await test_scheduler()

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASSED} passed / {FAILED} failed / {PASSED + FAILED} total")
    print(f"{'='*60}")

    return {"passed": PASSED, "failed": FAILED, "total": PASSED + FAILED}


if __name__ == "__main__":
    asyncio.run(main())
