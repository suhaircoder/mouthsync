# Deploying MouthSync — macOS, Windows, Linux

Guide for the **local stack** (backend + UI + MongoDB) and **publishing worker images** to Docker Hub / RunPod.  
GPU video rendering runs on **RunPod in the cloud** (same workflow on every desktop OS).

---

## Common steps (all platforms)

1. Clone the repo and `cd mouthsync/`.
2. Create `.env`: `make env` or `cp .env.example .env`.
3. Start UI + backend: `docker compose up -d --build` (or `make local-detached`).
4. Open the UI: http://localhost:3000
5. In settings, set URLs for **two** RunPod Pods (SadTalker + Wav2Lip).
6. Worker images for RunPod must be `linux/amd64` (see `make worker-*-publish`).

| Service | Port | URL |
|---------|------|-----|
| UI | 3000 | http://localhost:3000 |
| Backend API | 8000 | http://localhost:8000 |
| MongoDB | 27017 | backend only (not exposed to UI) |

---

## macOS

### Install

| Tool | How to install |
|------|----------------|
| **Git** | `xcode-select --install` or [git-scm.com](https://git-scm.com/download/mac) |
| **Docker Desktop** | [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |
| **Make** | `xcode-select --install` (Command Line Tools) |
| **curl** | included in Terminal |

Make sure Docker Desktop is **running** (menu bar icon).

**Apple Silicon (M1/M2/M3):** `make worker-*-publish` already builds `linux/amd64` for RunPod. Local `docker compose` may build for ARM — that is fine for UI/backend.

### Commands (Terminal / iTerm)

```bash
git clone <repo-url> mouthsync
cd mouthsync
make env
# edit .env if needed
make local-detached
```

Verify:

```bash
curl -sS http://127.0.0.1:8000/health
open http://localhost:3000
```

### Publish images to Docker Hub (Mac)

```bash
export DOCKER_USER=your_docker_hub_username
make hub-login
make worker-publish-ready
```

### Troubleshooting (macOS)

| Issue | Fix |
|-------|-----|
| `port is already allocated` (8000) | Old container: `docker compose down --remove-orphans`, `docker stop mouthsync-gateway-1` |
| `make: command not found` | Install Command Line Tools: `xcode-select --install` |
| Docker won’t start | Docker Desktop → Settings → Resources, restart the app |
| Slow builds on ARM | Expected; Hub push is still `amd64` for RunPod |

---

## Windows

Use **Docker Desktop + WSL 2** and an **Ubuntu (WSL)** terminal for the same bash commands as in this doc.

### Install

| Tool | How to install |
|------|----------------|
| **WSL 2** | PowerShell (admin): `wsl --install`, reboot |
| **Docker Desktop** | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) → enable **WSL 2 backend** |
| **Git** | [git-scm.com](https://git-scm.com/download/win) or `winget install Git.Git` |
| **Make** (in WSL) | `sudo apt update && sudo apt install -y make` |
| **Make** (no WSL) | optional [Chocolatey](https://chocolatey.org/): `choco install make` — WSL is simpler |

Clone into the WSL home directory, e.g. `~/projects/mouthsync` (not under `C:\` — Docker is much slower there).

### Commands (WSL — Ubuntu)

```bash
cd ~/projects
git clone <repo-url> mouthsync
cd mouthsync
make env
make local-detached
```

Verify:

```bash
curl -sS http://127.0.0.1:8000/health
```

Open in the Windows browser: http://localhost:3000 (port forwarding from Docker Desktop works from WSL).

### Without Make (PowerShell or CMD)

If `make` is not installed:

```powershell
cd mouthsync
copy .env.example .env
docker compose up -d --build
docker compose ps
```

Stop: `docker compose down`

### Publish images (Windows / WSL)

In **WSL**:

```bash
export DOCKER_USER=your_docker_hub_username
make hub-login
make worker-publish-ready
```

In **PowerShell** (instead of `export`):

```powershell
$env:DOCKER_USER="your_docker_hub_username"
docker login
# prefer WSL: make worker-publish-ready
```

### Troubleshooting (Windows)

| Issue | Fix |
|-------|-----|
| Docker: “WSL 2 required” | Docker Desktop → Settings → General → Use WSL 2 |
| `localhost:3000` won’t load | `docker compose ps`, restart Docker Desktop |
| Very slow disk I/O | Keep the repo on the WSL filesystem (`~/...`), not `/mnt/c/` |
| `curl` missing in PowerShell | Use WSL, or: `Invoke-WebRequest http://127.0.0.1:8000/health` |
| File permissions in WSL | `sudo chown -R $USER:$USER ~/projects/mouthsync` |

---

## Linux

### Install

**Ubuntu / Debian:**

```bash
sudo apt update
sudo apt install -y git make curl
# Docker Engine + Compose plugin:
# https://docs.docker.com/engine/install/ubuntu/
```

**Fedora / RHEL:**

```bash
sudo dnf install -y git make curl
# https://docs.docker.com/engine/install/fedora/
```

Add your user to the `docker` group and re-login:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

For **local SadTalker in Docker** (optional): [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

### Commands

```bash
git clone <repo-url> mouthsync
cd mouthsync
make env
make local-detached
```

Verify:

```bash
curl -sS http://127.0.0.1:8000/health
xdg-open http://localhost:3000   # or open manually
```

### Publish images (Linux)

```bash
export DOCKER_USER=your_docker_hub_username
make hub-login
make worker-publish-ready
```

Building `linux/amd64` for Hub is often faster on Linux than on Mac ARM.

### Troubleshooting (Linux)

| Issue | Fix |
|-------|-----|
| `permission denied` on docker.sock | `sudo usermod -aG docker $USER`, new login session |
| Port 8000 in use | `sudo ss -tlnp | grep 8000`, `docker compose down` |
| SELinux (Fedora) | Allow volume access or relax enforcing for a local test |
| No GPU in Docker | For local SadTalker: install NVIDIA Container Toolkit |

---

## RunPod (all platforms)

After `make worker-publish-ready` from **any** OS:

1. [runpod.io](https://www.runpod.io) → **Pods** → Deploy.
2. **Two** Pods: `mouthsync-worker-sadtalker` and `mouthsync-worker-wav2lip`.
3. GPU: RTX 3090 / 4090 / A5000 (avoid H100/L40 with the current PyTorch 2.1 Wav2Lip image unless you upgrade the base image).
4. **Expose HTTP ports:** `8000`.
5. In the UI: `https://<POD_ID>-8000.proxy.runpod.net`.

More detail: [RUNPOD.md](./RUNPOD.md).

---

## Command cheat sheet

| Action | macOS / Linux (bash) | Windows (no make) |
|--------|----------------------|-------------------|
| First run | `make env && make local-detached` | `copy .env.example .env` → `docker compose up -d --build` |
| Status | `make local-ps` or `docker compose ps` | `docker compose ps` |
| Logs | `make local-logs` | `docker compose logs -f` |
| Stop | `make local-down` | `docker compose down` |
| Rebuild | `docker compose up -d --build` | same |
| Health | `curl http://127.0.0.1:8000/health` | WSL: curl; PS: `Invoke-WebRequest` |

---

## Image documentation

| Image | README |
|-------|--------|
| Backend | [backend/README.md](./backend/README.md) |
| Frontend | [frontend/README.md](./frontend/README.md) |
| SadTalker worker | [runpod-worker-sadtalker/README.md](./runpod-worker-sadtalker/README.md) |
| Wav2Lip worker | [runpod-worker-wav2lip/README.md](./runpod-worker-wav2lip/README.md) |
