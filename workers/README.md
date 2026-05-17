# MouthSync worker registry

All workers expose the **same HTTP API** — only `WORKER_URL` changes in the UI; gateway and frontend stay the same.

| Use case | ID | Directory | GPU | Status |
|----------|-----|-----------|-----|--------|
| Neural lip-sync (lighter) | `wav2lip` | `runpod-worker-wav2lip/` | yes | **ready** |
| Best realtime quality | `musetalk` | `runpod-worker-musetalk/` | yes | scaffold |
| Most natural expression | `liveportrait` | `runpod-worker-liveportrait/` | yes | scaffold |
| CPU / weak GPU | `ultralight` | `runpod-worker-ultralight/` | no | scaffold |
| Ready-made realtime stack | `livetalking` | `runpod-worker-livetalking/` | yes | scaffold |
| Fast MVP (no neural net) | `lite` | `runpod-worker/` | no | **ready** |
| Talking head (offline) | `sadtalker` | `runpod-worker-sadtalker/` | yes | **ready** |

Full registry: [`registry.yaml`](./registry.yaml).

---

## Shared API contract

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | `status`: `ok` or `scaffold`; `ready`: true/false |
| `POST` | `/infer` | multipart `photo` + `audio` → MP4 |

Header `X-Worker-Key` when `WORKER_API_KEY` is set on the Pod.

RunPod: **Expose HTTP ports `8000`**, URL `https://<pod-id>-8000.proxy.runpod.net`.

---

## Build and publish

```bash
export DOCKER_USER=<username>
make hub-login
make worker-list
make worker-wav2lip-publish      # any id from the table
make worker-publish-ready        # lite + sadtalker + wav2lip
```

Image: `docker.io/<DOCKER_USER>/mouthsync-worker-<id>:latest`  
(for `lite`: `mouthsync-worker` without suffix).

---

## Add a new worker from template

```bash
./workers/new-worker.sh <id> "<Title>" "<upstream repo url>" [gpu|cpu]
```

1. Add an entry to `workers/registry.yaml`.
2. Implement `animate_face()` in `runpod-worker-<id>/` (reference: `runpod-worker-sadtalker/render_sadtalker.py`).
3. Replace `Dockerfile` (scaffold = API only; production = models + CUDA if needed).
4. Set `BACKEND_READY = True` in render module.
5. `make worker-<id>-publish`.

Template files: [`_template/`](./_template/).

---

## Reference implementation: SadTalker

```
runpod-worker-sadtalker/
├── main.py              # FastAPI, lifespan preload
├── render_sadtalker.py  # Engine.load() + generate()
├── Dockerfile           # PyTorch CUDA + upstream clone + checkpoints
└── BACKEND.md
```

Pattern:

1. **`render_*.py`** — model logic; `animate_face(photo, audio, out_mp4)`.
2. **`backend_info()`** — `backend`, `ready`, `device`, …
3. **`preload_models()`** — optional with `WORKER_PRELOAD=1`.
4. **`main.py`** — keep the HTTP contract; import from render only.

---

## Scaffold workers

`musetalk`, `liveportrait`, `ultralight`, `livetalking`:

- `GET /health` → `"status":"scaffold"`, `"ready":false`
- `POST /infer` → **501** until `render.py` is implemented

You can still build and deploy scaffolds to verify RunPod URL and port **8000**.

---

## Switching in the UI

One or more Pods — in MouthSync set **WORKER_URL** to the chosen worker’s proxy URL.
