# mouthsync-backend

Local **MouthSync backend** (FastAPI): photo/audio prep, history, orchestration of SadTalker and Wav2Lip workers.

Not published to Docker Hub by default — built by `docker compose` as image **`mouthsync-backend`**.

---

## Docker image (local)

| | |
|---|---|
| **Compose service** | `backend` |
| **Image name** | `mouthsync-backend:latest` (local build) |
| **Port** | `8000` → http://localhost:8000 |
| **Build context** | `backend/` |

Deploy on **macOS / Windows / Linux**: [../DEPLOY.md](../DEPLOY.md).

```bash
cd mouthsync
docker compose build backend
docker compose up -d backend mongo frontend
curl -sS http://127.0.0.1:8000/health
```

**Windows:** run these in **WSL** (recommended) or use `docker compose` from PowerShell without `make`.

---

## Responsibilities

- Face check and **photo prep** (crop, brightness, …)
- **Audio prep** (trim, gain, resample, …)
- `POST /api/generate` → SadTalker worker
- `POST /api/history/{id}/refine` → Wav2Lip worker
- **History** in MongoDB (default) or `backend/data/history/` (if `MONGODB_URI` unset)

---

## Configuration

Root **`.env`** (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `MONGODB_URI` | MongoDB connection (default in compose) |
| `WORKER_URL` | Default SadTalker Pod URL |
| `WAV2LIP_WORKER_URL` | Default Wav2Lip Pod URL |
| `WORKER_API_KEY` | `X-Worker-Key` for workers |

UI can override worker URLs via browser localStorage.

---

## Publish to Docker Hub (optional)

If you want a Hub image, pick a name and push manually, for example:

```bash
export DOCKER_USER=your_docker_hub_username
docker build -t docker.io/$DOCKER_USER/mouthsync-backend:latest ./backend
docker push docker.io/$DOCKER_USER/mouthsync-backend:latest
```

Hub link (after you create the repo):  
https://hub.docker.com/r/YOUR_DOCKER_USER/mouthsync-backend
