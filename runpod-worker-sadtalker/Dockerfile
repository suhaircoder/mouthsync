# SadTalker GPU worker for RunPod (linux/amd64 + NVIDIA).
# Build: make worker-sadtalker-publish  (from mouthsync/, DOCKER_USER set)
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SADTALKER_ROOT=/app/SadTalker \
    SADTALKER_CHECKPOINT_DIR=/app/SadTalker/checkpoints \
    SADTALKER_SIZE=256 \
    SADTALKER_PREPROCESS=crop \
    SADTALKER_STILL=1 \
    SADTALKER_BATCH_SIZE=2 \
    SADTALKER_PRELOAD=1 \
    PYTHONPATH=/app/SadTalker

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

WORKDIR /app/SadTalker

RUN git clone --depth 1 https://github.com/OpenTalker/SadTalker.git .

# Inference deps (skip gradio / demo-only packages to shrink image)
RUN grep -vE '^(gradio|av)' requirements.txt > /tmp/requirements_infer.txt \
    && pip install --upgrade pip \
    && pip install -r /tmp/requirements_infer.txt

RUN bash scripts/download_models.sh

WORKDIR /app/api

COPY requirements-api.txt main.py render_sadtalker.py ./
RUN pip install -r requirements-api.txt \
    && mkdir -p /app/api/temp_files

EXPOSE 8000

# Single worker process — one GPU job at a time
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
