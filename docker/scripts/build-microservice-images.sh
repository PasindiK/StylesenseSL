#!/usr/bin/env bash
# Build all four backend images for separate Docker Hub pushes / Azure VMs.
# Run from anywhere:
#   export DOCKERHUB_USER=yourdockerhub
#   bash docker/scripts/build-microservice-images.sh
#
# Optional push:
#   PUSH=1 bash docker/scripts/build-microservice-images.sh
#
# Azure VMs are typically amd64 — keep --platform when building on Apple Silicon.
#
# Image names (customize tags if needed):
#   ${DOCKERHUB_USER}/stylesense-agentic:latest       — main API (+ Neo4j on same VM usually)
#   ${DOCKERHUB_USER}/stylesense-data-mesh:latest
#   ${DOCKERHUB_USER}/stylesense-data-fabric:latest   — includes TensorFlow; large build
#   ${DOCKERHUB_USER}/stylesense-data-architecture:latest
#
# Vercel env (production build):
#   VITE_API_URL=https://<agentic-host>/api
#   VITE_DATA_MESH_API_URL=https://<mesh-host>
#   VITE_DATA_FABRIC_API_URL=https://<fabric-host>/api   (see frontend usages)
#   VITE_DATA_ARCH_API_URL=https://<arch-host>/api

set -euo pipefail

DOCKERHUB_USER="${DOCKERHUB_USER:?Set DOCKERHUB_USER (Docker Hub username or org)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PLATFORM="${PLATFORM:-linux/amd64}"
TAG="${TAG:-latest}"

build() {
  local file="$1"
  local image="$2"
  echo "=== Building ${DOCKERHUB_USER}/${image}:${TAG} (${file}) ==="
  docker build --platform "${PLATFORM}" -f "${file}" -t "${DOCKERHUB_USER}/${image}:${TAG}" .
}

build docker/Dockerfile.backend stylesense-agentic
build docker/backend/Dockerfile.data-mesh stylesense-data-mesh
build docker/backend/Dockerfile.data-fabric stylesense-data-fabric
build docker/backend/Dockerfile.data-architecture stylesense-data-architecture

if [[ "${PUSH:-0}" == "1" ]]; then
  echo "=== docker login (if needed), then pushing ==="
  for img in stylesense-agentic stylesense-data-mesh stylesense-data-fabric stylesense-data-architecture; do
    docker push "${DOCKERHUB_USER}/${img}:${TAG}"
  done
fi

echo "Done. List images: docker images ${DOCKERHUB_USER}/stylesense-*"
