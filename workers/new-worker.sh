#!/usr/bin/env bash
# Create a worker scaffold from _template.
# Usage: ./workers/new-worker.sh <id> "<Title>" "<upstream_url>" [gpu|cpu]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$ROOT/workers/_template"

id="${1:?id required, e.g. wav2lip}"
title="${2:?title required}"
upstream="${3:?upstream URL required}"
gpu="${4:-gpu}"
target="$ROOT/runpod-worker-$id"

if [[ -d "$target" ]]; then
  echo "Already exists: $target" >&2
  exit 1
fi

mkdir -p "$target"
for f in main.py render.py Dockerfile requirements-api.txt BACKEND.md .env.example .dockerignore; do
  sed -e "s/__BACKEND_ID__/$id/g" \
      -e "s/__BACKEND_TITLE__/$title/g" \
      -e "s|__UPSTREAM_URL__|$upstream|g" \
      -e "s/__GPU_REQUIRED__/$gpu/g" \
      "$TEMPLATE/$f" > "$target/$f"
done

echo "Created $target"
echo "Add entry to workers/registry.yaml if missing, then implement render.py"
