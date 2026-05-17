# MouthSync on RunPod — full guide

From zero to working generation: image on Docker Hub → Pod on RunPod → UI on your machine.

---

## Architecture

```
[Browser :3000]  →  [Gateway :8000]  →  [Worker on RunPod :8000]
     UI                  local Docker          GPU/CPU in cloud
```

- **UI and gateway** — on your machine (Docker Compose).
- **Worker** — your container image on RunPod; accepts photo + audio, returns MP4.
- Generation history is stored **on the gateway** (`gateway/data/history/`), not on RunPod.

---

## Requirements

| Requirement | Why |
|-------------|-----|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Build images and run local UI/gateway |
| [Docker Hub](https://hub.docker.com/) account | Publish image for RunPod |
| [RunPod](https://www.runpod.io/) account + balance | GPU/CPU Pod |
| `mouthsync` repo | Project code |

On Mac (Apple Silicon), the RunPod image is built for **`linux/amd64`** — already set in the Makefile.

---

## Part 1. Build and publish the worker image

### 1.1. Open the project

```bash
cd mouthsync
```

### 1.2. Log in to Docker Hub

```bash
export DOCKER_USER=your_docker_hub_username
make hub-login
```

Enter username and password **or** an [Access Token](https://hub.docker.com/settings/security) (recommended instead of password).

### 1.3. Build and push

```bash
make worker-publish
```

This:

- builds `./runpod-worker` for **linux/amd64**;
- tags `docker.io/<DOCKER_USER>/mouthsync-worker:latest`;
- pushes to Docker Hub.

First build may take **10–20 minutes** (opencv, mediapipe, ffmpeg).

### 1.4. Test the image locally (optional)

```bash
docker run --rm -p 8000:8000 docker.io/$DOCKER_USER/mouthsync-worker:latest
```

In another terminal:

```bash
curl -sS http://127.0.0.1:8000/health
```

Expected: `{"status":"ok"}`. Stop the container (`Ctrl+C`).

### 1.5. Make the image public (if RunPod cannot pull private)

Docker Hub → repository `mouthsync-worker` → **Settings** → **Public**.

---

## Part 1b. SadTalker GPU worker (optional)

Same API (`/health`, `/infer`), different image — SadTalker neural model. Requires a **GPU Pod**.

```bash
export DOCKER_USER=your_username
make worker-sadtalker-publish
```

Image: `docker.io/<DOCKER_USER>/mouthsync-worker-sadtalker:latest`

| Parameter | Value |
|-----------|--------|
| Build | 30–60+ min (PyTorch + checkpoints) |
| Disk | ≥ 20 GB |
| RunPod | **GPU** (RTX 3090/4090, etc.) |
| HTTP port | **8000** |

On the Pod set **Container Image** to `mouthsync-worker-sadtalker:latest`, not the lite `mouthsync-worker`.

In MouthSync UI you only change **WORKER_URL** to this Pod’s URL.

### Wav2Lip GPU worker (optional)

```bash
make worker-wav2lip-publish
```

Image: `mouthsync-worker-wav2lip:latest` — often faster than SadTalker; same RunPod rules (GPU, port 8000).

---

## Part 2. Create a Pod on RunPod (detailed)

Goal: run **only** the MouthSync worker in the cloud — your image from Docker Hub.  
RunPod Jupyter/SadTalker/ML templates **do not work** without rewriting the API.

### 2.0. Target state

| Parameter | Value |
|-----------|--------|
| Image | `docker.io/<DOCKER_USER>/mouthsync-worker:latest` |
| Container port | **8000** |
| Public URL | `https://<POD_ID>-8000.proxy.runpod.net` |
| Check | `GET /health` → `{"status":"ok"}` |

### 2.1. Before RunPod

1. Image is on Docker Hub after `make worker-publish` (Part 1).
2. Repository is **Public** or RunPod credentials are set for private.
3. Note the full image string, e.g.:

   `docker.io/alnosila1s/mouthsync-worker:latest`

4. (Recommended) Generate a worker secret:

   ```bash
   openssl rand -hex 24
   ```

   Save it — needed on the Pod and in MouthSync UI.

### 2.2. Sign in and open Pods

1. Open [https://www.runpod.io](https://www.runpod.io) and sign in.
2. Ensure you have balance (Pods bill while running).
3. Left menu: **Pods** (not Serverless).
4. Click **Deploy** / **+ GPU Pod** (wording varies).

### 2.3. Hardware (GPU / CPU)

Current lite MouthSync worker is **CPU** (OpenCV + MediaPipe); **GPU not required**.

| Option | When to use |
|--------|-------------|
| **Cheap CPU Pod** | Tests and short clips |
| **GPU** | SadTalker, Wav2Lip, or other neural backends |

Tips:

- Pick a **region** close to you.
- **Network volume** is **not** needed for MouthSync.
- **RAM**: ≥ 4 GB recommended.

### 2.4. Docker image (critical)

Use **your** image, not “PyTorch + Jupyter”.

#### Option A — Container Image field

1. Find **Container Image** / **Image Name**.
2. Paste the **full** name:

   `docker.io/<DOCKER_USER>/mouthsync-worker:latest`

3. **Do not** pick templates like Jupyter on port 8888 — different software and ports.

#### Option B — Custom template

1. **Templates** → **New Template** (once).
2. Image: full `docker.io/...` name.
3. **Container disk**: ≥ **10 GB**.
4. **Start command**: leave **empty** — image already runs uvicorn on 8000.
5. Select this template when creating the Pod.

#### Common image mistakes

| Mistake | Result |
|---------|--------|
| `mouthsync-worker:latest` without `docker.io/user/` | Pull may fail |
| Jupyter template on 8888 | 404 + Jupyter HTML in MouthSync |
| Stale `:latest` cache | Stop → Start Pod or create new Pod |

### 2.5. Ports and HTTP proxy (critical)

Worker listens on **port 8000** inside the container.

1. Find **Expose HTTP Ports** / **HTTP Ports** ([docs](https://docs.runpod.io/pods/configuration/expose-ports)).
2. Set **8000** (number only, or `8000/http` if the UI asks for protocol).
3. **Do not** use **8888** (Jupyter in foreign templates).
4. TCP/SSH ports are **not** needed for MouthSync.

After start, URL pattern:

`https://<POD_ID>-8000.proxy.runpod.net`

### 2.6. Environment variables

| Key | Value | Required? |
|-----|--------|-----------|
| `WORKER_API_KEY` | your random string | No, but **recommended** |

Without a key the worker accepts requests without auth (public URL — anyone can call it).

**Do not confuse:**

- `WORKER_API_KEY` — **your** MouthSync secret;
- RunPod account API key — for RunPod CLI, **not** the worker.

`WORKER_URL` is **not** needed on the Pod — set it in UI on your Mac.

### 2.7. Other Pod settings

| Field | Recommendation |
|-------|----------------|
| **Volume** | not needed |
| **Jupyter** | off / do not use |
| **Expose TCP** | not needed |

### 2.8. Deploy and wait

1. **Deploy** / **Create Pod**.
2. Statuses: **Pulling image** → **Running** (first start often **2–10 min**).
3. **Failed** → check **Logs** (2.10).

### 2.9. Worker URL

#### Formula

`https://<POD_ID>-8000.proxy.runpod.net`

- `<POD_ID>` — short Pod id (e.g. `ci6db85v6b21pq`).
- `8000` — port from **Expose HTTP Ports**.

Use **no** trailing slash and **no** `/health` in the UI field.

#### Method 1 — build URL yourself (most reliable)

1. [console.runpod.io/pods](https://www.console.runpod.io/pods)
2. Copy **Pod ID** from a **Running** Pod.
3. Build URL and test:

   ```bash
   curl -sS "https://<POD_ID>-8000.proxy.runpod.net/health"
   ```

   `{"status":"ok"}` means the URL is correct even if the UI showed no link.

#### Method 2 — Connect menu

Pod → **Connect** → **HTTP services** / port **8000**.  
If you only see Jupyter on **8888**, that is not MouthSync.

#### Method 3 — Edit Pod

**Edit Pod** → **Expose HTTP Ports** → add `8000` → wait for **Running**.

Without **8000** exposed, the proxy URL **does not exist**.

#### URL not found?

| Situation | Action |
|-----------|--------|
| Pod still pulling | Wait for **Running**, check **Logs** |
| No port 8000 | **Edit Pod** → add `8000` |
| Only Jupyter 8888 | Wrong template; use mouthsync image + 8000 |
| Looking in Serverless | Use **Pods** |
| Pod Stopped | **Start** or create new Pod |

**New Pod → new Pod ID → new URL.** Update MouthSync UI after Terminate.

### 2.10. Verify Pod (required)

```bash
curl -sS "https://<POD_ID>-8000.proxy.runpod.net/health"
```

With key:

```bash
curl -sS -H "X-Worker-Key: your_secret" \
  "https://<POD_ID>-8000.proxy.runpod.net/health"
```

From local gateway:

```bash
curl -sS "http://127.0.0.1:8000/api/worker-status" \
  -H "X-Worker-Url: https://<POD_ID>-8000.proxy.runpod.net" \
  -H "X-Worker-Key: your_secret"
```

Expected: `"ok": true`.

### 2.11. Troubleshooting

| Symptom | Check |
|---------|--------|
| Jupyter HTML, 404 | Port 8888 or wrong template → mouthsync image, port **8000** |
| Connection refused | Pod not **Running**; wait for pull |
| Image pull failed | Image name, public repo, Docker Hub login |
| 401 | Wrong `X-Worker-Key` |
| `curl /health` OK, UI fails | URL without slash; `make up-detached` |

**Pod logs** should show:

```text
Uvicorn running on http://0.0.0.0:8000
```

If you see Jupyter — wrong image or start command.

### 2.12. Stop / Start / delete

| Action | Effect |
|--------|--------|
| **Stop** | Pod stopped; URL down |
| **Start** | Running again; URL often unchanged |
| **Terminate** | Pod gone; new Deploy → **new URL** |

After tests: **Stop** Pod locally `make down`.

---

## Part 3. Run MouthSync locally (UI + gateway)

Worker is on RunPod; locally you only run **UI and gateway**.

### 3.1. `.env` file

```bash
cd mouthsync
make env
```

Edit `.env` (URL can be empty — set in UI):

```env
WORKER_URL=https://<POD_ID>-8000.proxy.runpod.net
WORKER_API_KEY=your_secret_if_any
WORKER_TIMEOUT_SEC=600
```

### 3.2. Start without local worker

```bash
make up-detached
```

After code changes:

```bash
make down
make up-build
```

Check:

```bash
make ps
```

Expect **frontend** (:3000) and **gateway** (:8000). **worker** service not needed in this mode.

### 3.3. Gateway checks

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/api/worker-status \
  -H "X-Worker-Url: https://<POD_ID>-8000.proxy.runpod.net" \
  -H "X-Worker-Key: your_secret"
```

---

## Part 4. Browser workflow

### 4.1. Open UI

[http://localhost:3000](http://localhost:3000)

### 4.2. Worker (RunPod) panel

1. **WORKER_URL** — Pod URL.
2. **WORKER_API_KEY** — same as on Pod (or empty).
3. **Save**.
4. **Test connection** — should report worker reachable.

Settings are in **browser** localStorage. After a **new Pod**, update URL here.

### 4.3. Generate

1. **Portrait** — JPG/PNG, face close-up.
2. **Speech** — WAV/MP3, etc.
3. **Generate video**.

First run may take seconds to a minute+ depending on audio length and Pod power.

**SadTalker/Wav2Lip:** RunPod HTTP proxy ~**100s** limit — use **5–15s** audio for tests; see gateway error message on 524.

### 4.4. Result and history

- Video in **Result**.
- Entry in **History** on the gateway (replay or delete).

---

## Part 5. Update image and redeploy

```bash
export DOCKER_USER=your_username
make worker-publish
```

On RunPod: **Stop** → **Start** or new Pod with `:latest`.

New Pod → new URL → update UI → **Test connection**.

---

## Part 6. Stop and save money

| Action | Where |
|--------|--------|
| Stop local UI/gateway | `make down` |
| Stop Pod | RunPod → **Stop** |
| Delete Pod | RunPod → **Terminate** |

---

## Part 7. Troubleshooting (summary)

| Symptom | Cause | Fix |
|---------|-------|-----|
| 404 + Jupyter HTML | Port 8888 or wrong template | `mouthsync-worker`, HTTP **8000** |
| Cannot reach worker | Pod down / bad URL | Pod **Running**, `curl .../health` |
| 401 | Key mismatch | Same `WORKER_API_KEY` on Pod and UI |
| 524 / timeout | RunPod proxy ~100s | Shorter audio; lite worker; other hosting |
| `worker_configured: false` | Empty URL | Fill WORKER_URL |
| Pull failed | Private image | Public repo or RunPod credentials |
| SadTalker 500 in logs | Bad audio | Valid WAV/MP3; check Pod logs |

---

## Command cheat sheet

```bash
export DOCKER_USER=username
make hub-login
make worker-publish
make worker-sadtalker-publish
make worker-wav2lip-publish

make env
make up-detached
make ps
make down

curl https://<pod>-8000.proxy.runpod.net/health
curl http://127.0.0.1:8000/api/worker-status -H "X-Worker-Url: https://<pod>-8000.proxy.runpod.net"
```

---

## Port map

| Service | Where | Port |
|---------|-------|------|
| UI | your machine | 3000 |
| Gateway | Docker on Mac | 8000 |
| MouthSync worker | RunPod | 8000 → `...-8000.proxy.runpod.net` |
| ~~Jupyter~~ | foreign templates | ~~8888~~ — **wrong** |
