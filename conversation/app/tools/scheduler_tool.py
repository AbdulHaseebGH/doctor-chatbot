# --------------------------------------------------------------------------
# conversation/app/tools/scheduler_tool.py
#
# Appointment Scheduler Tool — in-memory store with JSON file persistence.
# Functions: book_appointment, check_availability, list_appointments
# --------------------------------------------------------------------------

import json
import os
from datetime import datetime

# Persist appointments to a JSON file so data survives container restarts
def _get_appointments_file() -> str:
    return os.getenv("APPOINTMENTS_FILE", "/app/data/appointments.json")

# Valid clinic doctors
VALID_DOCTORS = {
    "ahmed": "Dr. Ahmed (General)",
    "alina": "Dr. Alina (Pediatrics)",
    "khan": "Dr. Khan (Cardiology)",
}

# Doctor availability (days of week, 0=Mon...6=Sun)
DOCTOR_DAYS = {
    "ahmed": [0, 1, 2, 3, 4, 5],   # Mon–Sat
    "alina": [0, 2, 4],             # Mon, Wed, Fri
    "khan":  [1, 3, 5],             # Tue, Thu, Sat
}

# Clinic hours
CLINIC_OPEN = 9   # 9am
CLINIC_CLOSE = 18 # 6pm


def _load_appointments() -> dict:
    """Load appointments from disk."""
    fpath = _get_appointments_file()
    os.makedirs(os.path.dirname(fpath) if os.path.dirname(fpath) else ".", exist_ok=True)
    if os.path.exists(fpath):
        try:
            with open(fpath, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_appointments(appointments: dict) -> None:
    """Persist appointments to disk."""
    fpath = _get_appointments_file()
    os.makedirs(os.path.dirname(fpath) if os.path.dirname(fpath) else ".", exist_ok=True)
    with open(fpath, "w") as f:
        json.dump(appointments, f, indent=2)


def _parse_doctor(doctor_name: str) -> tuple[str, str]:
    """Match a doctor name string to a known doctor key. Returns (key, display_name)."""
    name_lower = doctor_name.lower()
    for key, display in VALID_DOCTORS.items():
        if key in name_lower:
            return key, display
    return None, None


def _parse_hour(time_str: str) -> int | None:
    """Parse time strings like '5pm', '14:00', '2 pm' → integer hour."""
    import re
    time_str = time_str.strip().lower().replace(" ", "")
    # Try HH:MM format
    match = re.match(r"(\d{1,2}):(\d{2})", time_str)
    if match:
        return int(match.group(1))
    # Try hour with am/pm
    match = re.match(r"(\d{1,2})(am|pm)?", time_str)
    if match:
        hour = int(match.group(1))
        suffix = match.group(2)
        if suffix == "pm" and hour != 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        return hour
    return None


async def book_appointment(date: str, time: str, doctor: str, patient_name: str) -> dict:
    """
    Book an appointment.

    Args:
        date: Date string e.g. "2026-05-10" or "Monday" or "next Thursday"
        time: Time string e.g. "5pm", "14:00", "2 PM"
        doctor: Doctor name e.g. "Dr. Ahmed", "Khan", "Alina"
        patient_name: Patient's name

    Returns:
        {"status": "booked", "confirmation": "..."} or {"status": "error", "error": "..."}
    """
    doctor_key, doctor_display = _parse_doctor(doctor)
    if not doctor_key:
        return {"status": "error", "error": f"Unknown doctor '{doctor}'. Available: Dr. Ahmed, Dr. Alina, Dr. Khan."}

    hour = _parse_hour(time)
    if hour is None:
        return {"status": "error", "error": f"Could not parse time '{time}'. Please use format like '5pm' or '14:00'."}

    if not (CLINIC_OPEN <= hour < CLINIC_CLOSE):
        return {"status": "error", "error": f"Clinic is open {CLINIC_OPEN}am–{CLINIC_CLOSE-12}pm. Time {time} is outside clinic hours."}

    appointments = _load_appointments()
    slot_key = f"{date}_{doctor_key}_{hour:02d}:00"

    if slot_key in appointments:
        return {"status": "error", "error": f"That slot is already booked. Please choose a different time."}

    appointments[slot_key] = {
        "patient": patient_name,
        "doctor": doctor_display,
        "date": date,
        "time": f"{hour:02d}:00",
        "booked_at": datetime.now().isoformat(),
    }
    _save_appointments(appointments)

    confirmation = f"Appointment booked for {patient_name} with {doctor_display} on {date} at {hour:02d}:00. Reference: {slot_key[:16]}"
    return {"status": "booked", "confirmation": confirmation, "slot_key": slot_key}


async def check_availability(date: str, doctor: str) -> dict:
    """
    Check available time slots for a doctor on a given date.

    Returns:
        {"available_slots": ["09:00", "10:00", ...]} or {"status": "error", ...}
    """
    doctor_key, doctor_display = _parse_doctor(doctor)
    if not doctor_key:
        return {"status": "error", "error": f"Unknown doctor '{doctor}'."}

    appointments = _load_appointments()
    booked_hours = set()
    for key, appt in appointments.items():
        if appt["date"] == date and doctor_key in key:
            try:
                booked_hours.add(int(appt["time"].split(":")[0]))
            except Exception:
                pass

    all_slots = list(range(CLINIC_OPEN, CLINIC_CLOSE))
    available = [f"{h:02d}:00" for h in all_slots if h not in booked_hours]

    return {
        "doctor": doctor_display,
        "date": date,
        "available_slots": available,
        "booked_count": len(booked_hours),
    }


async def list_appointments(patient_name: str) -> dict:
    """
    List all appointments for a patient.

    Returns:
        {"appointments": [...]} or {"appointments": []}
    """
    appointments = _load_appointments()
    patient_appointments = [
        appt for appt in appointments.values()
        if patient_name.lower() in appt.get("patient", "").lower()
    ]
    return {"appointments": patient_appointments}


# Tool schema
SCHEDULER_TOOL_SCHEMA = {
    "name": "scheduler",
    "description": "Book, check, or list clinic appointments.",
    "functions": {
        "book_appointment": {"args": ["date", "time", "doctor", "patient_name"], "description": "Book appointment"},
        "check_availability": {"args": ["date", "doctor"], "description": "Check available slots"},
        "list_appointments": {"args": ["patient_name"], "description": "List patient appointments"},
    }
}
