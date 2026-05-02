# --------------------------------------------------------------------------
# conversation/app/tools/crm_tool.py
#
# CRM Tool — wraps the Memory microservice for patient data management.
# Functions: get_user, create_user, update_user
# --------------------------------------------------------------------------

import httpx
import os

MEMORY_URL = os.getenv("MEMORY_URL", "http://memory:8002")
TIMEOUT = 10


async def get_user(user_id: str) -> dict:
    """
    Retrieve a patient profile by patient_id.

    Returns:
        {"found": True, "profile": {...}} or {"found": False, "error": "..."}
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"{MEMORY_URL}/patient/{user_id}")
            data = resp.json()
            if data.get("found"):
                return {"found": True, "profile": data["profile"]}
            return {"found": False, "error": f"No patient found with id={user_id}"}
    except Exception as e:
        return {"found": False, "error": str(e)}


async def create_user(name: str, phone: str = None, age: int = None, symptom: str = None) -> dict:
    """
    Create a new patient profile in the memory service.

    Returns:
        {"status": "created", "patient_id": "..."}
    """
    import uuid
    patient_id = str(uuid.uuid4())[:8]
    payload = {
        "patient_id": patient_id,
        "name": name,
    }
    if phone:
        payload["phone"] = phone
    if age:
        payload["age"] = age
    if symptom:
        payload["symptom"] = symptom

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(f"{MEMORY_URL}/patient/update", json=payload)
            return {"status": "created", "patient_id": patient_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def update_user(patient_id: str, field: str, value: str) -> dict:
    """
    Update a specific field in a patient's profile.

    Supported fields: name, phone, age, symptom
    Returns:
        {"status": "updated"} or {"status": "error", "error": "..."}
    """
    allowed_fields = {"name", "phone", "age", "symptom"}
    if field not in allowed_fields:
        return {"status": "error", "error": f"Unknown field '{field}'. Allowed: {allowed_fields}"}

    payload = {"patient_id": patient_id, field: value}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(f"{MEMORY_URL}/patient/update", json=payload)
            return {"status": "updated", "field": field}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# Tool schema for LLM prompt injection
CRM_TOOL_SCHEMA = {
    "name": "crm",
    "description": "Manage patient records. Use get_user to look up a patient, create_user to register a new patient, update_user to modify a field.",
    "functions": {
        "get_user": {"args": ["user_id"], "description": "Get patient profile by ID"},
        "create_user": {"args": ["name", "phone?", "age?", "symptom?"], "description": "Create new patient"},
        "update_user": {"args": ["patient_id", "field", "value"], "description": "Update patient field (name/phone/age/symptom)"},
    }
}
