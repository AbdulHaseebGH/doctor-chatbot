# --------------------------------------------------------------------------
# ASR Service Dockerfile — faster-whisper on CPU (int8)
# Runs speech-to-text transcription using the Whisper "base" model.
# Optimised for CPU with int8 quantisation via CTranslate2.
# --------------------------------------------------------------------------
FROM python:3.11-slim

# Install system deps required by faster-whisper / ctranslate2
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the whisper base model so container starts instantly
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

COPY app/ .

EXPOSE 8004
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
