# MouthSync worker registry

Production pipeline uses **two** workers:

| Stage | ID | Directory | RunPod image |
|-------|-----|-----------|--------------|
| 1 — talking head | `sadtalker` | `runpod-worker-sadtalker/` | `mouthsync-worker-sadtalker` |
| 2 — lip refine | `wav2lip` | `runpod-worker-wav2lip/` | `mouthsync-worker-wav2lip` |

Full registry: [`registry.yaml`](./registry.yaml).

---

## Shared API

| Worker | `GET /health` | Main endpoint |
|--------|---------------|---------------|
| SadTalker | yes | `POST /infer` (photo + audio → MP4) |
| Wav2Lip | yes, `refine_supported` | `POST /refine` (video + audio → MP4) |

Header `X-Worker-Key` when `WORKER_API_KEY` is set on the Pod.

RunPod: **Expose HTTP ports `8000`**, URL `https://<pod-id>-8000.proxy.runpod.net`.

---

## Build and publish

```bash
export DOCKER_USER=<username>
make hub-login
make worker-list
make worker-sadtalker-publish
make worker-wav2lip-publish
make worker-publish-ready   # both
```

---

## Add a new worker from template

```bash
./workers/new-worker.sh <id> "<Title>" "<upstream repo url>" [gpu|cpu]
```

Template: [`_template/`](./_template/). Reference: `runpod-worker-sadtalker/`.

---

## Local SadTalker (optional GPU)

```bash
docker compose --profile sadtalker-worker up --build worker-sadtalker
```

Set **WORKER_URL** in the UI to `http://127.0.0.1:9001`.
