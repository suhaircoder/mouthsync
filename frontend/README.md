# mouthsync-frontend

React + Vite UI for MouthSync: upload portrait and audio, two-stage pipeline (SadTalker → Wav2Lip), history, worker settings.

Not published to Docker Hub by default — built by `docker compose` as image **`mouthsync-frontend`**.

---

## Docker image (local)

| | |
|---|---|
| **Compose service** | `frontend` |
| **Image name** | `mouthsync-frontend:latest` (local build) |
| **Port** | `3000` → http://localhost:3000 |
| **Build context** | `frontend/` |

Deploy on **macOS / Windows / Linux**: [../DEPLOY.md](../DEPLOY.md).

```bash
cd mouthsync
docker compose up -d --build
```

API calls are proxied to the **backend** service (`PROXY_API_TARGET=http://backend:8000`).

---

## Development on host (optional)

```bash
cd frontend
npm install
npm run dev
```

Set `PROXY_API_TARGET=http://127.0.0.1:8000` if the backend runs locally.

---

## Publish to Docker Hub (optional)

```bash
export DOCKER_USER=your_docker_hub_username
docker build -t docker.io/$DOCKER_USER/mouthsync-frontend:latest ./frontend
docker push docker.io/$DOCKER_USER/mouthsync-frontend:latest
```

Hub link (after you create the repo):  
https://hub.docker.com/r/YOUR_DOCKER_USER/mouthsync-frontend
