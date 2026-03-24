# 🏥 City Medical Clinic — Conversational AI Receptionist

A fully local, production-style conversational AI system simulating a medical clinic front desk receptionist with **voice capabilities**. Built for CS 4063 - Natural Language Processing.

## 🎯 Business Use Case

**Doctor's Front Desk Assistant** — An AI receptionist named "Sara" that:
- Greets patients and collects their information
- Listens to symptoms and directs to appropriate doctor
- Schedules appointments
- Maintains patient history across sessions
- Operates strictly within clinic domain
- **Supports voice input and audio responses**

---

## 🏗️ System Architecture
```
Browser (React + Voice UI)
      │ WebSocket / HTTP
      ▼
API Gateway :8000
      │ HTTP
      ├──► Conversation Manager :8001
      │         │ HTTP
      │         ├──► Memory Service :8002 ◄──► SQLite DB
      │         └──► LLM Engine :8003 ◄──► LM Studio :1234
      ├──► Memory Service :8002
      ├──► ASR Service :8004 (faster-whisper, Speech→Text)
      └──► TTS Service :8005 (piper-tts, Text→Speech)
```

### Voice Pipeline Flow
```
Browser Mic → WebM audio blob
    → POST /api/voice/transcribe (ASR service)
    → transcribed text displayed in input
    → POST via WebSocket to /ws/chat (existing LLM chat)
    → LLM response text
    → POST /api/voice/synthesize (TTS service)
    → audio stream → browser plays audio
```

### Microservices

| Service | Port | Responsibility |
|---------|------|----------------|
| API Gateway | 8000 | WebSocket handler, request routing, session creation, voice proxy |
| Conversation Manager | 8001 | Session orchestration, prompt building, SNR filtering |
| Memory Service | 8002 | Short/long term memory, SQLite CRUD, patient profiles |
| LLM Engine | 8003 | LM Studio API wrapper, streaming inference |
| **ASR Service** | **8004** | **Speech-to-text via faster-whisper (int8, CPU)** |
| **TTS Service** | **8005** | **Text-to-speech via piper-tts (CPU)** |

---

## 🧠 Memory Architecture

### Short-Term Memory (Within Session)
- Sliding window of last 20 conversation turns
- **SNR (Signal-to-Noise Ratio) filtering** — only meaningful clinical information is retained
- Signal keywords: symptoms, names, phone numbers, appointment times, medical terms

### Long-Term Memory (Across Sessions)
- Patient profiles stored in SQLite database
- Automatic extraction of patient info using LLM after each turn
- Smart patient matching by name + phone number combination
- Returning patients recognized automatically

---

## 🎤 Voice Agent

### ASR (Speech-to-Text)
- **Model**: faster-whisper `base` (~140 MB)
- **Quantization**: int8 via CTranslate2
- **Performance**: <500ms for 5-second audio clip
- **Features**: VAD filtering, beam_size=1 for speed

### TTS (Text-to-Speech)
- **Engine**: piper-tts
- **Voice**: en_US-lessac-medium (clear American English)
- **Performance**: <300ms first audio chunk
- **Output**: 16-bit PCM WAV at 22050 Hz

### Concurrency
- Max 4 simultaneous voice sessions
- Returns HTTP 503 with clear message if capacity exceeded
- Uses asyncio.Semaphore for async queue management

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

### 3. Start All Backend Services (Docker)
```bash
docker-compose up --build
```

This starts 6 services:
- Gateway (8000), Conversation (8001), Memory (8002), LLM (8003)
- ASR (8004), TTS (8005)

> **Note**: First build will take longer as ASR downloads the Whisper model (~140MB) and TTS downloads the Piper voice model (~100MB).

Verify all services:
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8005/health
```

### 4. Start Frontend
```bash
cd frontend
npm install
npm start
```

Frontend runs on `http://localhost:3000`

---

## 🌐 Deployment

### Frontend (Vercel)
The frontend is deployable on Vercel. Set these environment variables:
```
REACT_APP_API_URL=https://your-backend-url.onrender.com
REACT_APP_WS_URL=wss://your-backend-url.onrender.com
```

### Backend (Render)
A unified backend is available in the `backend/` folder with `render.yaml` config:
```bash
cd backend
# Contains: main.py, routes/, services/, Dockerfile, render.yaml
```

**Environment variables for Render:**
| Variable | Description | Default |
|----------|-------------|---------|
| `CONVERSATION_URL` | Conversation service URL | `http://conversation:8001` |
| `MEMORY_URL` | Memory service URL | `http://memory:8002` |
| `LLM_URL` | LLM service URL | `http://llm:8003` |
| `ASR_URL` | ASR service URL | `http://asr:8004` |
| `TTS_URL` | TTS service URL | `http://tts:8005` |

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
| **POST** | **`/api/voice/transcribe`** | **Audio file → transcribed text** |
| **POST** | **`/api/voice/synthesize`** | **Text → audio WAV stream** |
| **POST** | **`/api/voice/chat`** | **Full pipeline: audio → LLM → audio** |

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

### Voice API Details

**POST /api/voice/transcribe**
```bash
curl -X POST http://localhost:8000/api/voice/transcribe \
  -F "file=@audio.webm"
```
Response: `{"text": "I need to see a doctor", "duration_ms": 420}`

**POST /api/voice/synthesize**
```bash
curl -X POST http://localhost:8000/api/voice/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "How can I help you?"}' \
  --output speech.wav
```

**POST /api/voice/chat** (full pipeline)
```bash
curl -X POST http://localhost:8000/api/voice/chat \
  -F "file=@audio.webm" \
  -F "session_id=your-session-id" \
  --output response.wav
```

---

## 📁 Project Structure
```
doctor-chatbot/
├── gateway/                 # API Gateway (Port 8000)
│   ├── app/main.py          # WebSocket, REST routes, voice proxy
│   ├── Dockerfile
│   └── requirements.txt
├── conversation/            # Conversation Manager (Port 8001)
│   ├── app/
│   │   ├── main.py
│   │   └── prompts.py       # System prompt with guardrails
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
├── asr/                     # ASR Service (Port 8004) ← NEW
│   ├── app/main.py          # faster-whisper transcription
│   ├── Dockerfile
│   └── requirements.txt
├── tts/                     # TTS Service (Port 8005) ← NEW
│   ├── app/main.py          # piper-tts synthesis
│   ├── Dockerfile
│   └── requirements.txt
├── backend/                 # Unified Backend (for Render) ← NEW
│   ├── main.py
│   ├── routes/
│   │   ├── chat.py
│   │   └── voice.py
│   ├── services/
│   │   ├── asr_service.py
│   │   ├── tts_service.py
│   │   ├── llm_service.py
│   │   └── memory_service.py
│   ├── prompts.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── render.yaml
├── frontend/                # React Frontend ← IMPROVED
│   └── src/
│       ├── App.js           # Voice UI, FAQ chips, timestamps
│       └── App.css          # Navy/indigo dark theme
├── docker-compose.yml       # All 6 services
├── postman_collection.json
└── README.md
```

---

## ✅ System Features

- ✅ Fully local inference — no cloud APIs
- ✅ **Voice input via browser microphone (ASR)**
- ✅ **Audio responses via TTS playback**
- ✅ **Voice concurrency limiter (max 4 sessions)**
- ✅ Instruction-tuned conversational responses
- ✅ **Improved LLM guardrails** (domain lock, prompt injection defense, emergency protocol)
- ✅ Short-term memory with SNR filtering
- ✅ Long-term patient profiles across sessions
- ✅ CPU-optimized inference via Q4_K_M quantization
- ✅ Real-time streaming token output
- ✅ Multi-session support (ChatGPT-style)
- ✅ **Redesigned UI** (navy/indigo theme, FAQ chips, timestamps, copy buttons)
- ✅ **Mobile responsive layout**
- ✅ Microservices architecture
- ✅ Dockerized deployment
- ✅ **Render-ready backend** with render.yaml

---

## ⚠️ Known Limitations

- LLM inference speed is slow on CPU-only hardware (~24s average) — voice pipeline adds minimal overhead
- LM Studio must be running separately before starting Docker services
- Patient matching relies on phone number — patients without phone may not be recognized
- First Docker build is slower due to model downloads (ASR ~140MB, TTS ~100MB)
- Voice requires microphone permission in browser

---

## Honor Policy

All code, architecture, and implementation is original work by the group. Generative AI tools were used for assistance and code suggestions, with full understanding and explanation capability of all components.
