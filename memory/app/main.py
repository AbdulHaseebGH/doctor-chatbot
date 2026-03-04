# memory/app/main.py
from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3, json, os
from datetime import datetime
from typing import Optional

app = FastAPI(title="Memory Service")
DB_PATH = "/app/data/patients.db"

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT,
            age INTEGER,
            medical_history TEXT DEFAULT '[]',
            past_appointments TEXT DEFAULT '[]',
            preferences TEXT DEFAULT '{}',
            last_seen TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            patient_id TEXT,
            started_at TEXT,
            short_term TEXT DEFAULT '[]',
            summary TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- SNR Filtering ----------
SIGNAL_KEYWORDS = [
    "pain", "fever", "appointment", "doctor", "name", "age", "phone",
    "symptoms", "headache", "cough", "chest", "breathe", "dizzy",
    "tuesday", "monday", "wednesday", "thursday", "friday", "saturday",
    "morning", "afternoon", "evening", "years", "old", "number",
    "insurance", "emergency", "prescription", "medicine", "allergic"
]

def is_signal(text: str) -> bool:
    text_lower = text.lower()
    # Noise: very short messages or pure greetings
    if len(text.split()) < 4:
        return False
    return any(keyword in text_lower for keyword in SIGNAL_KEYWORDS)

# ---------- Schemas ----------
class SessionCreate(BaseModel):
    session_id: str
    # patient_id: str = None
    patient_id: Optional[str] = None

class TurnAdd(BaseModel):
    session_id: str
    role: str
    content: str

class PatientUpdate(BaseModel):
    patient_id: str
    name: str = None
    phone: str = None
    age: int = None
    symptom: str = None

# ---------- Endpoints ----------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "memory"}

@app.post("/session/create")
async def create_session(data: SessionCreate):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO sessions (session_id, patient_id, started_at, short_term) VALUES (?,?,?,?)",
        (data.session_id, data.patient_id, datetime.now().isoformat(), "[]")
    )
    conn.commit()
    conn.close()
    return {"status": "created", "session_id": data.session_id}

@app.post("/session/add-turn")
async def add_turn(data: TurnAdd):
    conn = get_db()
    row = conn.execute("SELECT short_term FROM sessions WHERE session_id=?", (data.session_id,)).fetchone()
    if not row:
        conn.close()
        return {"status": "session not found"}

    history = json.loads(row["short_term"])

    # SNR filtering — always keep assistant turns, filter user turns
    if data.role == "user":
        if is_signal(data.content):
            history.append({"role": data.role, "content": data.content, "is_signal": True})
        else:
            history.append({"role": data.role, "content": data.content, "is_signal": False})
    else:
        history.append({"role": data.role, "content": data.content, "is_signal": True})

    # Keep last 20 turns max
    if len(history) > 20:
        history = history[-20:]

    conn.execute("UPDATE sessions SET short_term=? WHERE session_id=?",
                 (json.dumps(history), data.session_id))
    conn.commit()
    conn.close()
    return {"status": "added", "is_signal": is_signal(data.content)}

@app.get("/session/{session_id}/context")
async def get_context(session_id: str):
    conn = get_db()
    session = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    if not session:
        conn.close()
        return {"history": [], "patient_profile": None}

    history = json.loads(session["short_term"])
    # Return only signal turns for context + last 6 turns regardless
    signal_turns = [t for t in history if t.get("is_signal", True)]
    recent_turns = history[-6:] if len(history) > 6 else history
    # Merge: signal + recent, deduplicated
    seen = set()
    merged = []
    for turn in signal_turns + recent_turns:
        key = turn["content"]
        if key not in seen:
            seen.add(key)
            merged.append({"role": turn["role"], "content": turn["content"]})

    # Get patient profile if linked
    patient_profile = None
    if session["patient_id"]:
        patient = conn.execute("SELECT * FROM patients WHERE patient_id=?",
                               (session["patient_id"],)).fetchone()
        if patient:
            patient_profile = dict(patient)

    conn.close()
    return {"history": merged, "patient_profile": patient_profile}

@app.post("/patient/update")
async def update_patient(data: PatientUpdate):
    conn = get_db()
    existing = conn.execute("SELECT * FROM patients WHERE patient_id=?",
                            (data.patient_id,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO patients (patient_id, name, phone, age, last_seen) VALUES (?,?,?,?,?)",
            (data.patient_id, data.name, data.phone, data.age, datetime.now().isoformat())
        )
    else:
        if data.name:
            conn.execute("UPDATE patients SET name=? WHERE patient_id=?", (data.name, data.patient_id))
        if data.phone:
            conn.execute("UPDATE patients SET phone=? WHERE patient_id=?", (data.phone, data.patient_id))
        if data.age:
            conn.execute("UPDATE patients SET age=? WHERE patient_id=?", (data.age, data.patient_id))
        if data.symptom:
            patient = conn.execute("SELECT medical_history FROM patients WHERE patient_id=?",
                                   (data.patient_id,)).fetchone()
            history = json.loads(patient["medical_history"])
            history.append({"symptom": data.symptom, "date": datetime.now().isoformat()})
            conn.execute("UPDATE patients SET medical_history=? WHERE patient_id=?",
                         (json.dumps(history), data.patient_id))
        conn.execute("UPDATE patients SET last_seen=? WHERE patient_id=?",
                     (datetime.now().isoformat(), data.patient_id))
    conn.commit()
    conn.close()
    return {"status": "updated"}

@app.get("/patient/{patient_id}")
async def get_patient(patient_id: str):
    conn = get_db()
    patient = conn.execute("SELECT * FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
    conn.close()
    if not patient:
        return {"found": False}
    return {"found": True, "profile": dict(patient)}

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.get("/patient/search")
async def search_patient(name: str = None, phone: str = None):
    conn = get_db()
    
    if name and phone:
        # Best match — both name and phone
        patient = conn.execute(
            "SELECT * FROM patients WHERE LOWER(name) LIKE ? AND phone LIKE ?",
            (f"%{name.lower()}%", f"%{phone}%")
        ).fetchone()
    elif phone:
        # Phone is more unique than name
        patient = conn.execute(
            "SELECT * FROM patients WHERE phone LIKE ?",
            (f"%{phone}%",)
        ).fetchone()
    elif name:
        # Name only — least reliable but still useful
        patient = conn.execute(
            "SELECT * FROM patients WHERE LOWER(name) LIKE ?",
            (f"%{name.lower()}%",)
        ).fetchone()
    else:
        conn.close()
        return {"found": False}
    
    conn.close()
    if not patient:
        return {"found": False}
    return {"found": True, "patient_id": patient["patient_id"], "profile": dict(patient)}