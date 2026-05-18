# Run commands from the mouthsync directory (next to docker-compose.yml).
#
# Docker Hub (RunPod worker):
#   export DOCKER_USER=your_login
#   make hub-login
#   make worker-list
#   make worker-sadtalker-publish

include workers/workers.mk

COMPOSE := docker compose
DOCKER_USER ?=
DOCKER_IMAGE ?= $(DOCKER_USER)/mouthsync-worker
SADTALKER_IMAGE ?= $(DOCKER_USER)/mouthsync-worker-sadtalker
DOCKER_TAG ?= latest
# RunPod is usually linux/amd64; on Apple Silicon build with this or the Pod may not start
DOCKER_PLATFORM ?= linux/amd64
FULL_IMAGE := docker.io/$(DOCKER_IMAGE):$(DOCKER_TAG)
SADTALKER_FULL_IMAGE := docker.io/$(SADTALKER_IMAGE):$(DOCKER_TAG)

.PHONY: help env up up-build up-detached down logs ps build \
	local-up local-down local-detached local-logs local-ps \
	hub-check hub-login worker-list worker-publish-ready

help:
	@echo "MouthSync — make targets"
	@echo ""
	@echo "  make env             create .env from .env.example if missing"
	@echo "  make up              docker compose up (logs in terminal)"
	@echo "  make up-build        same + rebuild images"
	@echo "  make up-detached     background: up -d --build"
	@echo "  make down            stop and remove containers"
	@echo "  make logs            tail logs for all services"
	@echo "  make ps              container status"
	@echo "  make build           build compose images only"
	@echo ""
	@echo "Local stack (backend + UI, workers on RunPod):"
	@echo "  make local-up        logs in terminal"
	@echo "  make local-detached  background (usual local run)"
	@echo "  make local-down      stop stack with worker"
	@echo "  make local-ps        container status"
	@echo "  make local-logs      logs"
	@echo ""
	@echo "Workers (registry: workers/README.md):"
	@echo "  make worker-list              table of all backends"
	@echo "  make worker-<id>-publish      sadtalker | wav2lip"
	@echo "  make worker-publish-ready     production-ready workers only"
	@echo "  ./workers/new-worker.sh       new scaffold from _template"

env:
	@test -f .env \
		|| (cp .env.example .env && echo "[make] Created .env from .env.example — set WORKER_URL (and WORKER_API_KEY if needed).")

up: env-check
	$(COMPOSE) up

up-build: env-check
	$(COMPOSE) up --build

up-detached: env-check
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

build: env-check
	$(COMPOSE) build

local-up: env-check
	$(COMPOSE) up --build

local-detached: env-check
	$(COMPOSE) up -d --build

local-down:
	$(COMPOSE) down

local-ps:
	$(COMPOSE) ps

local-logs:
	$(COMPOSE) logs -f

hub-check:
	@command -v docker >/dev/null || (echo "[make] Docker is required" && exit 1)
	@test -n "$(DOCKER_USER)" || (echo "[make] Set DOCKER_USER, e.g. export DOCKER_USER=myname" && exit 1)

hub-login:
	docker login

# Internal: ensure .env exists before up
env-check:
	@test -f .env || cp .env.example .env 2>/dev/null || true
