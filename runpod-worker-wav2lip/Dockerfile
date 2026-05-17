# Wav2Lip GPU worker for RunPod (linux/amd64 + NVIDIA).
# Build: make worker-wav2lip-publish  (from mouthsync/, DOCKER_USER set)
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WAV2LIP_ROOT=/app/Wav2Lip \
    WAV2LIP_CHECKPOINT=/app/Wav2Lip/checkpoints/wav2lip_gan.pth \
    WAV2LIP_PRELOAD=1 \
    PYTHONPATH=/app/Wav2Lip

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    wget \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/Wav2Lip

RUN git clone --depth 1 https://github.com/Rudrabha/Wav2Lip.git . \
    && sed -i 's/cv2\.cv2\.ROTATE_90_CLOCKWISE/cv2.ROTATE_90_CLOCKWISE/g' inference.py

# upstream requirements.txt: numpy==1.17 does not build on Py3.10 (setuptools/distutils).
COPY requirements-docker.txt /tmp/requirements-docker.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements-docker.txt

RUN mkdir -p checkpoints temp \
    && wget -q --show-progress -O checkpoints/wav2lip_gan.pth \
        "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth"

WORKDIR /app/api

COPY requirements-api.txt main.py render_wav2lip.py ./
RUN pip install -r requirements-api.txt \
    && mkdir -p /app/api/temp_files

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
