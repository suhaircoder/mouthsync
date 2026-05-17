# MouthSync

**Lip-sync** from a portrait and audio → short video. Local **gateway** (`gateway/`, FastAPI) and **UI** (`frontend/`, React + Vite); heavy rendering runs on a **remote worker**. Configure via `.env` at the repo root (template: `.env.example`).

**Worker registry (Wav2Lip, MuseTalk, SadTalker, …):** [workers/README.md](./workers/README.md)

**Full RunPod walkthrough (from scratch):** [RUNPOD.md](./RUNPOD.md) *(Russian)*

---

## Generation history

After each successful generation the gateway stores:

- video `output.mp4`
- source photo and audio
- metadata (filenames, timestamp)

Files live under **`gateway/data/history/`** (Docker volume: `./gateway/data`).

In the UI, the **History** panel lets you replay and delete entries.

API:

- `GET /api/history` — list entries
- `GET /api/history/{id}/video` — video file
- `DELETE /api/history/{id}` — delete entry

---

## Worker settings in the UI

At **http://localhost:3000**, section **Worker (RunPod)**:

- **WORKER_URL** and **WORKER_API_KEY** are stored in this browser’s **localStorage**.
- After each **new RunPod Pod**, paste the new URL and click **Save** — editing `.env` is optional.
- **Test connection** calls `GET /api/worker-status` on the gateway (same URL used for generation).
- If the URL field is **empty**, the gateway falls back to **`WORKER_URL` from `.env`** (handy for default docker compose).

Priority: **UI values** → **gateway `.env`**.

---

## `WORKER_URL` and `WORKER_API_KEY`

| Variable | Purpose |
|----------|---------|
| **`WORKER_URL`** | Public URL of **your** service on the RunPod Pod **without** the `/infer` path (no trailing slash). The gateway appends `/infer` automatically. Example: `https://<pod-id>-8000.proxy.runpod.net` |
| **`WORKER_API_KEY`** | This is **not** your RunPod account API key. It is a **secret you choose** in the worker’s Pod env vars and the same value in local `.env` — the gateway sends it as header `X-Worker-Key`. Leave empty in `.env` if the worker has no key. |

The RunPod dashboard API key (REST/CLI) is **not** required for this worker.

---

## 1. Build and publish the lite worker image

Build context: **`runpod-worker/`**.

### Via Makefile (recommended)

```bash
cd mouthsync
export DOCKER_USER=<your_docker_hub_username>
make hub-login          # once: Docker Hub login/token
make worker-publish     # build linux/amd64 + push
```

Image: `docker.io/<DOCKER_USER>/mouthsync-worker:latest`

Local smoke test before push:

```bash
make worker-build-hub
docker run --rm -p 8000:8000 docker.io/$DOCKER_USER/mouthsync-worker:latest
curl http://127.0.0.1:8000/health
```

### Manual (equivalent)

```bash
docker build --platform linux/amd64 \
  -t docker.io/<DOCKER_USER>/mouthsync-worker:latest ./runpod-worker
docker login
docker push docker.io/<DOCKER_USER>/mouthsync-worker:latest
```

On Apple Silicon Macs, **`--platform linux/amd64`** matters — RunPod Pods are usually amd64.

---

## 1b. SadTalker worker (GPU, neural)

Second worker with the **same API** (`/health`, `/infer`), rendering via [SadTalker](https://github.com/OpenTalker/SadTalker). Directory: **`runpod-worker-sadtalker/`**.

| | `runpod-worker` (lite) | `runpod-worker-sadtalker` |
|---|------------------------|---------------------------|
| Quality | MVP, mouth ROI shift | More realistic, neural |
| Hardware | CPU | **NVIDIA GPU** |
| Image size | ~hundreds of MB | several GB (models baked in) |
| RunPod | CPU Pod OK | **GPU Pod required** |

### Build and push

```bash
export DOCKER_USER=<username>
make hub-login
make worker-sadtalker-publish
```

Image: `docker.io/<DOCKER_USER>/mouthsync-worker-sadtalker:latest`

`/health` after start (model load may take 1–3 min):

```json
{"status":"ok","backend":"sadtalker","device":"cuda","models_loaded":true,"size":256,...}
```

### RunPod

Same as lite, but:

- **Container image:** `docker.io/<DOCKER_USER>/mouthsync-worker-sadtalker:latest`
- **GPU:** RTX 3090 / 4090 or similar
- **Expose HTTP ports:** `8000`
- **Container disk:** **≥ 20 GB**

Set **WORKER_URL** in the MouthSync UI to the SadTalker Pod URL (`https://<id>-8000.proxy.runpod.net`).

Switch workers by changing **WORKER_URL** only (lite CPU vs SadTalker GPU). UI and gateway stay the same.

---

## 1c. Wav2Lip worker (GPU, lighter neural lip-sync)

Directory: **`runpod-worker-wav2lip/`**. Same HTTP API; rendering via [Wav2Lip](https://github.com/Rudrabha/Wav2Lip).

```bash
export DOCKER_USER=<username>
make worker-wav2lip-publish
```

Image: `docker.io/<DOCKER_USER>/mouthsync-worker-wav2lip:latest`

Typically faster and lighter than SadTalker; lip-sync quality between lite and SadTalker. **GPU Pod** recommended, port **8000**, disk **≥ 15 GB**.

---

## 2. Create a RunPod Pod

1. Sign in at [runpod.io](https://www.runpod.io) → **Pods**.
2. **Deploy** a new Pod.
3. **Container image:** `docker.io/<DOCKER_USER>/mouthsync-worker:latest` (or `-sadtalker` / `-wav2lip`).
4. **Expose HTTP ports:** **`8000`** — uvicorn listens on 8000 inside the container. Without this, no public proxy URL.  
   Docs: [Expose ports](https://docs.runpod.io/pods/configuration/expose-ports).
5. (Optional) **Environment:** `WORKER_API_KEY` = long random string; same in local `.env`.
6. Wait for **Running**.

---

## 3. Get `WORKER_URL`

Public URL format:

`https://<POD_ID>-8000.proxy.runpod.net`

Copy the full URL **without** a trailing slash. In `.env`:

```env
WORKER_URL=https://<POD_ID>-8000.proxy.runpod.net
```

Check from your machine:

```bash
curl -sS "https://<POD_ID>-8000.proxy.runpod.net/health"
```

Expected: `{"status":"ok",...}`.

With `WORKER_API_KEY` on the worker:

```bash
curl -sS -H "X-Worker-Key: <YOUR_SECRET>" "https://<POD_ID>-8000.proxy.runpod.net/health"
```

---

## 4. Run locally

```bash
cd mouthsync
make env
# Edit .env: WORKER_URL (RunPod) or http://worker:8000 for local worker
make local-detached
make local-ps
```

Gateway + UI only (worker on RunPod): `make up-detached` and set URL in UI or `.env`.

- UI: [http://localhost:3000](http://localhost:3000)  
- Gateway API: [http://localhost:8000](http://localhost:8000)  

Vite proxies `/api` to the **`gateway`** service; the gateway calls RunPod via `WORKER_URL`.

---

## 5. RunPod HTTP proxy limit

The public HTTP proxy has a **~100 second** connection limit (Cloudflare **524** on long jobs). SadTalker/Wav2Lip on long audio may hit this. Use shorter clips for tests, lite worker for quick tries, or async hosting later.

---

## 6. Local worker in Docker (no RunPod)

For debugging without RunPod, use profile `local-worker` and in `.env`:

```env
WORKER_URL=http://worker:8000
```

```bash
make local-up          # logs in terminal
# or
make local-detached
```

Worker on host: **http://localhost:9000**. Stop: `make local-down`.

SadTalker locally (NVIDIA):

```bash
docker compose --profile sadtalker-worker up --build worker-sadtalker
# UI: http://127.0.0.1:9001
```

---

## Makefile

From **`mouthsync/`**:

| Command | Action |
|---------|--------|
| `make help` | list targets |
| `make env` | create `.env` from `.env.example` if missing |
| `make up-detached` | gateway + UI (RunPod worker via UI/env) |
| `make down` | stop (without local-worker profile) |
| `make local-detached` | **recommended**: UI + gateway + lite worker |
| `make local-down` | stop full local stack |
| `make local-ps` / `make local-logs` | status / logs |
| `make hub-login` | Docker Hub login |
| `make worker-list` | all workers and status |
| `make worker-publish` | build + push lite worker |
| `make worker-sadtalker-publish` | SadTalker image |
| `make worker-wav2lip-publish` | Wav2Lip image |
| `make worker-publish-ready` | push all production-ready workers |

---

## Environment files

- Project root: **`.env`** (do not commit; see **`.gitignore`** and **`.env.example`**).
- Also: `gateway/.env.example` — reminder about root `.env`.
