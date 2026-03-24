# --------------------------------------------------------------------------
# TTS Service Dockerfile — piper-tts on CPU
# Runs text-to-speech synthesis using piper with the en_US-lessac-medium voice.
# Piper is extremely fast on CPU (~10x real-time), ideal for low-latency voice.
# --------------------------------------------------------------------------
FROM python:3.11-slim

# Install system deps for audio processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends wget && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the piper voice model so container starts instantly
# Using en_US-lessac-medium — clear, natural-sounding, fast on CPU
RUN mkdir -p /models/piper && \
    wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
         -O /models/piper/en_US-lessac-medium.onnx && \
    wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" \
         -O /models/piper/en_US-lessac-medium.onnx.json

COPY app/ .

EXPOSE 8005
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
