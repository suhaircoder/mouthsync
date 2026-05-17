# __BACKEND_TITLE__

| | |
|---|---|
| **ID** | `__BACKEND_ID__` |
| **Image** | `docker.io/<DOCKER_USER>/mouthsync-worker-__BACKEND_ID__:latest` |
| **GPU** | __GPU_REQUIRED__ |
| **Status** | scaffold — implement `render.py` |

## Upstream

__UPSTREAM_URL__

## Bringing to production

1. Copy logic from **`runpod-worker-sadtalker/`** (Dockerfile with models, `render_*.py` with `Engine.load()` + `generate()`).
2. Set `BACKEND_READY = True` in `render.py` after working inference.
3. Replace `Dockerfile` with an image that includes upstream dependencies (PyTorch / CUDA if needed).
4. `make worker-__BACKEND_ID__-publish`
5. RunPod: GPU/CPU per registry table, **Expose HTTP ports: 8000**, URL in MouthSync UI.

## API (do not change)

- `GET /health`
- `POST /infer` — multipart `photo` + `audio` → MP4
- Header `X-Worker-Key` if `WORKER_API_KEY` is set
