# mouthsync-worker-sadtalker

GPU worker for **MouthSync stage 1**: portrait + audio → talking-head MP4 ([SadTalker](https://github.com/OpenTalker/SadTalker)).

Used with the MouthSync backend ([project README](../../README.md)) — `POST /api/generate` → worker `POST /infer`.

---

## Docker Hub

Replace **`YOUR_DOCKER_USER`** with your Docker Hub login (same as `export DOCKER_USER=...` when publishing).

| | |
|---|---|
| **Hub repository** | https://hub.docker.com/r/YOUR_DOCKER_USER/mouthsync-worker-sadtalker |
| **Image tag** | `docker.io/YOUR_DOCKER_USER/mouthsync-worker-sadtalker:latest` |

```bash
docker pull docker.io/YOUR_DOCKER_USER/mouthsync-worker-sadtalker:latest
```

**RunPod → Container Image:** paste the full name above (with your username).

---

## RunPod

| Setting | Value |
|---------|--------|
| GPU | NVIDIA (RTX 3090 / 4090 / A5000 recommended) |
| Expose HTTP ports | `8000` |
| Container disk | ≥ 20 GB |
| Public URL | `https://<POD_ID>-8000.proxy.runpod.net` |

In MouthSync UI set **WORKER_URL** (stage 1) to that URL (no trailing slash).

Optional env on the Pod:

| Key | Default | Description |
|-----|---------|-------------|
| `WORKER_API_KEY` | *(empty)* | If set, clients must send header `X-Worker-Key` |
| `SADTALKER_SIZE` | `256` | Model resolution |
| `SADTALKER_PRELOAD` | `1` | Load models at startup |
| `SADTALKER_BATCH_SIZE` | `2` | Inference batch size |

---

## HTTP API

| Method | Path | Body | Response |
|--------|------|------|----------|
| `GET` | `/health` | — | `{"status":"ok","backend":"sadtalker",...}` |
| `POST` | `/infer` | multipart: `photo`, `audio` | `video/mp4` |

```bash
curl -sS "https://<pod>-8000.proxy.runpod.net/health"
```

---

## Build and publish (from source)

Works the same on **macOS, Linux, and Windows (WSL)**. Full guide: [../DEPLOY.md](../DEPLOY.md).

```bash
cd mouthsync
export DOCKER_USER=your_docker_hub_username   # PowerShell: $env:DOCKER_USER="..."
make hub-login
make worker-sadtalker-publish
```

Build context: this directory (`runpod-worker-sadtalker/`). Platform: `linux/amd64` (RunPod). On **Apple Silicon**, Makefile cross-builds for amd64 automatically.

---

## Local smoke test (GPU)

```bash
docker run --rm -p 9001:8000 \
  docker.io/$DOCKER_USER/mouthsync-worker-sadtalker:latest
curl -sS http://127.0.0.1:9001/health
```

---

## Notes

- First start may take **1–3 minutes** while models load (`/health` may show `loading` briefly).
- RunPod HTTP proxy ~**100 s** limit — use short audio for tests.
- Do **not** use RunPod Jupyter / generic SadTalker templates on port 8888 — this image exposes the MouthSync API on **8000**.
