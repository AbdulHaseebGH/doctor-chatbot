# --------------------------------------------------------------------------
# ASR Service Dockerfile — faster-whisper (batch) + Vosk (streaming)
#
# faster-whisper: high-accuracy batch POST /transcribe (fallback-quality)
# Vosk:           real-time streaming WS /ws/asr-stream with VAD
# --------------------------------------------------------------------------
FROM python:3.11-slim

# System deps: ffmpeg for whisper, wget+unzip for Vosk model download
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg wget unzip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download faster-whisper base model (batch transcription)
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

# Download Vosk small English model (~40MB, streaming ASR)
RUN mkdir -p /app/models && \
    wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -O /tmp/vosk-model.zip && \
    unzip -q /tmp/vosk-model.zip -d /app/models/ && \
    mv /app/models/vosk-model-small-en-us-0.15 /app/models/vosk-model-en && \
    rm /tmp/vosk-model.zip

COPY app/ .

EXPOSE 8004
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
