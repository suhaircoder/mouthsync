# Wav2Lip

| | |
|---|---|
| **ID** | `wav2lip` |
| **Image** | `docker.io/<DOCKER_USER>/mouthsync-worker-wav2lip:latest` |
| **GPU** | yes (recommended) |
| **Status** | ready for build |

## Upstream

https://github.com/Rudrabha/Wav2Lip

## Build and RunPod

```bash
export DOCKER_USER=<username>
make worker-wav2lip-publish
```

Pod: **GPU**, **Expose HTTP ports `8000`**, disk **≥ 15 GB**.

## Env (optional)

| Key | Default |
|-----|---------|
| `WAV2LIP_CHECKPOINT` | `/app/Wav2Lip/checkpoints/wav2lip_gan.pth` |
| `WAV2LIP_BATCH_SIZE` | `128` |
| `WAV2LIP_FPS` | `25` |
| `WORKER_PRELOAD` | `1` |

## API

- `GET /health` → `"backend":"wav2lip"`, `"ready":true`
- `POST /infer` — photo + audio → MP4 (static face)
- `POST /refine` — **video** + audio → MP4 (lip-sync on existing talking-head video)
- `POST /infer` — `photo` + `audio` → MP4

Often faster than SadTalker; RunPod HTTP proxy ~100s limit — use short audio for tests.
