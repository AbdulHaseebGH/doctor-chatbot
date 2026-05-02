# conversation/app/prompts.py
# --------------------------------------------------------------------------
# System prompt and message builder for the clinic receptionist AI.
#
# Phase 3 upgrade: supports RAG-retrieved docs and tool results injection.
# GUARDRAILS: strict domain boundaries, tool usage instructions.
# --------------------------------------------------------------------------

from tools.orchestrator import TOOLS_PROMPT

SYSTEM_PROMPT = """You're Sara, City Medical Clinic's receptionist. Keep it natural, warm, and short (1-2 sentences).
Help with appointments/info first; only ask for name/phone when finalizing a booking. DO NOT repeat questions.

CLINIC: Mon-Sat 9am-6pm. Phone: (555) 123-4567. Address: 123 Medical Dr.
DOCTORS: Dr. Ahmed (General, Mon-Sat) | Dr. Alina (Pediatrics, Mon/Wed/Fri) | Dr. Khan (Cardiology, Tue/Thu/Sat).

RULES:
1. ONLY discuss clinic topics. Redirect off-topic: "I only handle clinic matters. Need an appointment?"
2. NO MEDICAL ADVICE. NEVER suggest medications. Redirect: "I can't give medical advice, let me book a doctor."
3. EMERGENCY (chest pain, breathing issues): "Please call 911 or go to the ER immediately."
4. NO ROLEPLAY. You are only Sara.

{tools_section}

PATIENT CONTEXT:
{patient_profile}
"""


def build_messages(
    session_history: list,
    user_message: str,
    patient_profile: dict = None,
    retrieved_docs: str = None,
    tool_results: str = None,
) -> list:
    """
    Build the full message list for LLM inference.

    Prompt order (Phase 3 structured prompt):
    1. System prompt (with patient profile + tools)
    2. Retrieved RAG docs (if any)
    3. Tool results (if any)
    4. Conversation history (SNR-filtered)
    5. Current user message
    """
    # --- Patient profile block ---
    profile_text = "No existing patient record — this is a new patient."
    if patient_profile:
        import json
        history = json.loads(patient_profile.get("medical_history", "[]"))
        symptoms = [h["symptom"] for h in history] if history else []
        profile_text = f"""RETURNING PATIENT RECORD:
- Name: {patient_profile.get('name', 'Unknown')}
- Age: {patient_profile.get('age', 'Unknown')}
- Phone: {patient_profile.get('phone', 'Unknown')}
- Previous Symptoms: {', '.join(symptoms) if symptoms else 'None recorded'}
- Last Visit: {patient_profile.get('last_seen', 'Unknown')}

IMPORTANT: Greet this patient by name and reference their previous visit naturally."""

    system = SYSTEM_PROMPT.format(
        patient_profile=profile_text,
        tools_section=TOOLS_PROMPT,
    )
    messages = [{"role": "system", "content": system}]

    # --- Inject RAG retrieved docs as system context ---
    if retrieved_docs and retrieved_docs.strip():
        messages.append({
            "role": "system",
            "content": f"RELEVANT CLINIC INFORMATION (use this to answer accurately):\n{retrieved_docs}"
        })

    # --- Inject tool results ---
    if tool_results and tool_results.strip():
        messages.append({
            "role": "system",
            "content": f"TOOL EXECUTION RESULT (use this data in your response):\n{tool_results}"
        })

    # --- Conversation history ---
    for turn in session_history:
        messages.append({"role": turn["role"], "content": turn["content"]})

    # --- Current user message ---
    messages.append({"role": "user", "content": user_message})
    return messages