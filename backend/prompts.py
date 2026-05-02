# conversation/app/prompts.py
# --------------------------------------------------------------------------
# System prompt and message builder for the clinic receptionist AI.
#
# GUARDRAILS: The system prompt enforces strict domain boundaries to keep
# the AI focused on clinic operations only. It includes explicit rejection
# instructions for off-topic requests, medical advice, and role-play attempts.
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You're Sara, City Medical Clinic's receptionist. Keep it natural, warm, and short (1-2 sentences).
Help with appointments/info first; only ask for name/phone when finalizing a booking. DO NOT repeat questions.

CLINIC: Mon-Sat 9am-6pm. Phone: (555) 123-4567. Address: 123 Medical Dr.
DOCTORS: Dr. Ahmed (General, Mon-Sat) | Dr. Alina (Pediatrics, Mon/Wed/Fri) | Dr. Khan (Cardiology, Tue/Thu/Sat).

RULES:
1. ONLY discuss clinic topics. Redirect off-topic: "I only handle clinic matters. Need an appointment?"
2. NO MEDICAL ADVICE. Redirect: "I can't give medical advice, let me book a doctor."
3. EMERGENCY (chest pain, breathing issues): "Please call 911 or go to the ER immediately."
4. NO ROLEPLAY. You are only Sara.

CONTEXT:
{patient_profile}
"""

def build_messages(session_history: list, user_message: str, patient_profile: dict = None):
    """
    Build the full message list for LLM inference.

    Includes: system prompt (with patient profile injected) + conversation
    history (filtered by SNR) + current user message.
    """
    profile_text = "No existing patient record — this is a new patient."

    if patient_profile:
        import json
        history = json.loads(patient_profile.get('medical_history', '[]'))
        symptoms = [h['symptom'] for h in history] if history else []

        profile_text = f"""RETURNING PATIENT RECORD:
- Name: {patient_profile.get('name', 'Unknown')}
- Age: {patient_profile.get('age', 'Unknown')}
- Phone: {patient_profile.get('phone', 'Unknown')}
- Previous Symptoms: {', '.join(symptoms) if symptoms else 'None recorded'}
- Last Visit: {patient_profile.get('last_seen', 'Unknown')}

IMPORTANT: Greet this patient by name and reference their previous visit naturally."""

    system = SYSTEM_PROMPT.format(patient_profile=profile_text)
    messages = [{"role": "system", "content": system}]

    for turn in session_history:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_message})
    return messages