# --------------------------------------------------------------------------
# conversation/app/tools/orchestrator.py
#
# Tool Orchestrator — parses LLM output for tool calls and executes them.
#
# Detection strategy: regex-based JSON scanning (compatible with small LLMs
# like Qwen2.5-3B that may not reliably produce strict function-call format).
#
# Tool call format expected in LLM output:
#   {"tool": "scheduler", "function": "book_appointment", "arguments": {...}}
# --------------------------------------------------------------------------

import re
import json
from typing import Optional

from .crm_tool import get_user, create_user, update_user
from .scheduler_tool import book_appointment, check_availability, list_appointments
from .faq_tool import search_faq
from .calculator_tool import calculate


# ---------------------------------------------------------------------------
# Tool descriptions — injected into the system prompt so the LLM knows
# what tools exist and when to use them.
# ---------------------------------------------------------------------------

TOOLS_PROMPT = """
AVAILABLE TOOLS (use when action is needed):
To call a tool, output ONLY this JSON (nothing else on that line):
{"tool": "<tool_name>", "function": "<function_name>", "arguments": {<args>}}

Tools:
1. crm — Patient records
   - get_user(user_id): Look up patient by ID
   - create_user(name, phone?, age?, symptom?): Register new patient
   - update_user(patient_id, field, value): Update patient record

2. scheduler — Appointments
   - book_appointment(date, time, doctor, patient_name): Book appointment
   - check_availability(date, doctor): Check available slots
   - list_appointments(patient_name): View patient's appointments

3. faq — Clinic knowledge base
   - search_faq(query): Search clinic info, procedures, policies

4. calculator — Math
   - calculate(expression): Evaluate arithmetic expression

Only call a tool when you need real data. For general questions, respond normally.
"""


# ---------------------------------------------------------------------------
# Parser — extracts tool call JSON from raw LLM output text
# ---------------------------------------------------------------------------

def parse_tool_call(llm_output: str) -> tuple[Optional[dict], str]:
    """
    Scan LLM output for a tool call JSON object.

    Returns:
        Tuple of (Parsed dict, raw JSON string)
        or (None, "") if no valid tool call found.
    """
    # Find all top-level JSON objects by tracking brace depth
    def extract_json_objects(text: str) -> list[str]:
        objects = []
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    objects.append(text[start:i+1])
                    start = -1
        return objects

    candidates = extract_json_objects(llm_output)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if "tool" in data and "function" in data:
                return data, candidate
        except json.JSONDecodeError:
            continue

    return None, ""


# ---------------------------------------------------------------------------
# Executor — dispatches tool call to the correct function
# ---------------------------------------------------------------------------

async def execute_tool(tool_call: dict) -> dict:
    """
    Execute a parsed tool call.

    Args:
        tool_call: {"tool": "...", "function": "...", "arguments": {...}}

    Returns:
        Tool result dict (varies by tool).
    """
    tool_name = tool_call.get("tool", "").lower()
    function_name = tool_call.get("function", "").lower()
    arguments = tool_call.get("arguments", {})

    print(f"[TOOL] Executing {tool_name}.{function_name}({arguments})")

    try:
        # ---- CRM Tool ----
        if tool_name == "crm":
            if function_name == "get_user":
                return await get_user(arguments.get("user_id", ""))
            elif function_name == "create_user":
                return await create_user(**{k: v for k, v in arguments.items()})
            elif function_name == "update_user":
                return await update_user(
                    arguments.get("patient_id", ""),
                    arguments.get("field", ""),
                    arguments.get("value", "")
                )

        # ---- Scheduler Tool ----
        elif tool_name == "scheduler":
            if function_name == "book_appointment":
                return await book_appointment(
                    date=arguments.get("date", ""),
                    time=arguments.get("time", ""),
                    doctor=arguments.get("doctor", ""),
                    patient_name=arguments.get("patient_name", "")
                )
            elif function_name == "check_availability":
                return await check_availability(
                    date=arguments.get("date", ""),
                    doctor=arguments.get("doctor", "")
                )
            elif function_name == "list_appointments":
                return await list_appointments(arguments.get("patient_name", ""))

        # ---- FAQ Tool ----
        elif tool_name == "faq":
            if function_name == "search_faq":
                return await search_faq(arguments.get("query", ""))

        # ---- Calculator Tool ----
        elif tool_name == "calculator":
            if function_name == "calculate":
                return await calculate(arguments.get("expression", ""))

        return {"error": f"Unknown tool '{tool_name}' or function '{function_name}'"}

    except Exception as e:
        print(f"[TOOL] Execution error: {e}")
        return {"error": str(e)}


def format_tool_result(tool_call: dict, result: dict) -> str:
    """
    Format tool result for injection into the LLM prompt.
    """
    tool_name = tool_call.get("tool", "unknown")
    function_name = tool_call.get("function", "unknown")
    return f"[Tool Result: {tool_name}.{function_name}]\n{json.dumps(result, indent=2)}"
