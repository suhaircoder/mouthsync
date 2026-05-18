# mouthsync-worker-wav2lip

GPU worker for **MouthSync stage 2**: existing video + audio → lip-sync refined MP4 ([Wav2Lip](https://github.com/Rudrabha/Wav2Lip)).

Used with the MouthSync backend (`POST /api/history/{id}/refine` → worker `POST /refine`).

---

## Docker Hub

Replace **`YOUR_DOCKER_USER`** with your Docker Hub login (same as `export DOCKER_USER=...` when publishing).

| | |
|---|---|
| **Hub repository** | https://hub.docker.com/r/YOUR_DOCKER_USER/mouthsync-worker-wav2lip |
| **Image tag** | `docker.io/YOUR_DOCKER_USER/mouthsync-worker-wav2lip:latest` |

```bash
docker pull docker.io/YOUR_DOCKER_USER/mouthsync-worker-wav2lip:latest
```

**RunPod → Container Image:** paste the full name above (separate Pod from SadTalker).

---

## RunPod

| Setting | Value |
|---------|--------|
| GPU | NVIDIA (RTX 3090 / 4090 / A5000 recommended) |
| Expose HTTP ports | `8000` |
| Container disk | ≥ 15 GB |
| Public URL | `https://<POD_ID>-8000.proxy.runpod.net` |

In MouthSync UI set **Wav2Lip URL** (stage 2) to that URL (no trailing slash).

Optional env on the Pod:

| Key | Default | Description |
|-----|---------|-------------|
| `WORKER_API_KEY` | *(empty)* | If set, header `X-Worker-Key` required |
| `WAV2LIP_CHECKPOINT` | `/app/Wav2Lip/checkpoints/wav2lip_gan.pth` | Model weights |
| `WAV2LIP_BATCH_SIZE` | `128` | Wav2Lip batch size |
| `WAV2LIP_FACE_DET_BATCH_SIZE` | `16` | Face detection batch |
| `WAV2LIP_FPS` | `25` | FPS hint for video inputs |
| `WORKER_PRELOAD` | `1` | Verify checkpoint at startup |

---

## HTTP API

| Method | Path | Body | Response |
|--------|------|------|----------|
| `GET` | `/health` | — | `refine_supported: true`, `backend: wav2lip` |
| `POST` | `/refine` | multipart: `video`, `audio` | `video/mp4` (refined) |
| `POST` | `/infer` | multipart: `photo`, `audio` | `video/mp4` (static face, optional) |

Stage 2 in MouthSync uses **`/refine` only**.

```bash
curl -sS "https://<pod>-8000.proxy.runpod.net/health"
# Expect: "refine_supported": true
```

---

## Build and publish (from source)

Works the same on **macOS, Linux, and Windows (WSL)**. Full guide: [../DEPLOY.md](../DEPLOY.md).

```bash
cd mouthsync
export DOCKER_USER=your_docker_hub_username
make hub-login
make worker-wav2lip-publish
```

Build context: this directory (`runpod-worker-wav2lip/`). Includes librosa patches and browser-friendly MP4 transcoding.

---

## Local smoke test (GPU)

```bash
docker run --rm -p 9002:8000 \
  docker.io/$DOCKER_USER/mouthsync-worker-wav2lip:latest
curl -sS http://127.0.0.1:9002/health
```

---

## Notes

- Requires a **separate** RunPod Pod from SadTalker (stage 1).
- RunPod HTTP proxy ~**100 s** limit — use short clips for tests.
- PyTorch **2.1** image: avoid H100/L40 unless you upgrade the base image; prefer RTX 3090/4090 class GPUs.
