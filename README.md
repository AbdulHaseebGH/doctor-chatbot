# 🏥 City Medical Clinic — Conversational AI Receptionist

A fully local, production-style conversational AI system simulating a medical clinic front desk receptionist. Built for CS 4063 - Natural Language Processing, Assignment 2.

## 🎯 Business Use Case

**Doctor's Front Desk Assistant** — An AI receptionist named "Sara" that:
- Greets patients and collects their information
- Listens to symptoms and directs to appropriate doctor
- Schedules appointments
- Maintains patient history across sessions
- Operates strictly within clinic domain

---

## 🏗️ System Architecture
```
Browser (React)
      │ WebSocket
      ▼
API Gateway :8000
      │ HTTP
      ├──► Conversation Manager :8001
      │         │ HTTP
      │         ├──► Memory Service :8002 ◄──► SQLite DB
      │         └──► LLM Engine :8003 ◄──► LM Studio :1234
      └──► Memory Service :8002
```

### Microservices

| Service | Port | Responsibility |
|---------|------|----------------|
| API Gateway | 8000 | WebSocket handler, request routing, session creation |
| Conversation Manager | 8001 | Session orchestration, prompt building, SNR filtering |
| Memory Service | 8002 | Short/long term memory, SQLite CRUD, patient profiles |
| LLM Engine | 8003 | LM Studio API wrapper, streaming inference |

---

## 🧠 Memory Architecture

### Short-Term Memory (Within Session)
- Sliding window of last 20 conversation turns
- **SNR (Signal-to-Noise Ratio) filtering** — only meaningful clinical information is retained
- Signal keywords: symptoms, names, phone numbers, appointment times, medical terms
- Noise discarded: greetings, filler words, short acknowledgements

### Long-Term Memory (Across Sessions)
- Patient profiles stored in SQLite database
- Automatic extraction of patient info using LLM after each turn
- Smart patient matching by name + phone number combination
- Returning patients recognized automatically — profile injected into system prompt
- Cross-session context: "Welcome back Ahmed! I see you previously had chest pain"

### SNR Filtering Logic
```python
SIGNAL_KEYWORDS = [
    "pain", "fever", "appointment", "doctor", "name", "age", "phone",
    "symptoms", "headache", "chest", "breathe", "dizzy", "morning",
    "afternoon", "years", "old", "number", "insurance", "emergency"
]

def is_signal(text: str) -> bool:
    if len(text.split()) < 4:
        return False  # Too short = noise
    return any(keyword in text.lower() for keyword in SIGNAL_KEYWORDS)
```

---

## 🤖 Model Selection

| Property | Value |
|----------|-------|
| Model | Qwen2.5-3B-Instruct |
| Quantization | Q4_K_M (4-bit) |
| Inference Engine | LM Studio (llama.cpp backend) |
| Model Size | ~2.1 GB |
| RAM Usage | ~2.5 GB |
| Runs on | CPU only |

**Justification:** Qwen2.5-3B-Instruct-Q4_K_M was selected as it falls within the assignment's recommended 0.6B–4B range, runs efficiently on CPU via LM Studio/llama.cpp, and provides coherent multi-turn dialogue for a medical receptionist use case without requiring GPU acceleration.

---

## ⚡ Performance Benchmarks

### Inference Latency (Non-Streaming, Direct LLM Service)

| Test Query | Response Time |
|------------|--------------|
| Appointment request | 15.3s |
| Symptom description | 29.3s |
| Clinic hours query | 28.2s |
| **Average** | **24.3s** |

### Hardware
- CPU: Intel Core i7-6820HQ @ 2.70GHz (4 cores, 8 threads, Skylake)
- RAM: 16GB
- GPU: None (CPU-only inference)
- Storage: 1TB NVMe SSD

### Streaming Performance
- First token latency: ~2-3 seconds
- Perceived response time with streaming: significantly better than raw numbers suggest
- Streaming makes 24s average feel like real-time to users

---

## 🚀 Setup Instructions

### Prerequisites
- Docker Desktop
- LM Studio with `Qwen2.5-3B-Instruct-Q4_K_M` loaded and server running on port 1234
- Node.js v22+

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd doctor-chatbot
```

### 2. Start LM Studio
- Open LM Studio
- Load `Qwen2.5-3B-Instruct-Q4_K_M`
- Start Local Server on port 1234

### 3. Start Backend Services
```bash
docker-compose up --build
```

Verify all services:
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

### 4. Start Frontend
```bash
cd frontend
npm install
npm start
```

Frontend runs on `http://localhost:3000`

---

## 📁 Project Structure
```
doctor-chatbot/
├── gateway/                 # API Gateway (Port 8000)
│   ├── app/main.py
│   ├── Dockerfile
│   └── requirements.txt
├── conversation/            # Conversation Manager (Port 8001)
│   ├── app/
│   │   ├── main.py
│   │   └── prompts.py
│   ├── Dockerfile
│   └── requirements.txt
├── memory/                  # Memory Service (Port 8002)
│   ├── app/main.py
│   ├── data/patients.db
│   ├── Dockerfile
│   └── requirements.txt
├── llm/                     # LLM Engine (Port 8003)
│   ├── app/main.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                # React Frontend
│   └── src/
│       ├── App.js
│       └── App.css
├── docker-compose.yml
├── postman_collection.json
└── README.md
```

---

## 🔌 API Reference

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Gateway health check |
| POST | `/session` | Create new chat session |
| DELETE | `/session/{id}` | Delete session |
| GET | `/patient/{id}` | Get patient profile |
| GET | `/patient/search?name=&phone=` | Search patient |

### WebSocket
```
ws://localhost:8000/ws/chat/{session_id}
```
**Send:**
```json
{"message": "I need an appointment"}
```
**Receive (streaming):**
```json
{"token": "Hello"}
{"token": " Ahmed"}
{"token": "", "done": true}
```

---

## ✅ System Features

- ✅ Fully local inference — no cloud APIs
- ✅ Instruction-tuned conversational responses
- ✅ Short-term memory with SNR filtering
- ✅ Long-term patient profiles across sessions
- ✅ CPU-optimized inference via Q4_K_M quantization
- ✅ Real-time streaming token output
- ✅ Multi-session support (ChatGPT-style)
- ✅ Microservices architecture
- ✅ Dockerized deployment
- ✅ React frontend with dark theme

---

## ⚠️ Known Limitations

- Inference speed is slow on CPU-only hardware (~24s average)
- LM Studio must be running separately before starting Docker services
- Patient matching relies on phone number — patients without phone on file may not be recognized across sessions
- Model occasionally goes off-domain despite strict system prompt
- No persistent frontend state — chat history lost on page refresh

---

## 🧪 Testing

### Run All Health Checks
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

### Test Memory
```bash
# Check patient profile
curl http://localhost:8002/patient/{patient_id}

# Check session context
curl http://localhost:8002/session/{session_id}/context
```

### Import Postman Collection
Import `postman_collection.json` into Postman for full API testing.

---

## Honor Policy

All code, architecture, and implementation is original work by the group. Generative AI tools were used for assistance and code suggestions, with full understanding and explanation capability of all components.
