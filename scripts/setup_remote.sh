#!/usr/bin/env bash
# =====================================================================
# Remote setup for the Azure GPU VM (run ON the VM, via provision_azure.sh).
# Installs NVIDIA stack, Ollama (CUDA), the repo, and pulls the pinned model.
# Idempotent: safe to re-run.
# =====================================================================
set -euo pipefail

MODEL_TAG="${MODEL_TAG:-deepseek-r1:14b}"
REPO_URL="${REPO_URL:-https://github.com/ericmedlock/MSAI-LLM-PERFORMANCE.git}"

echo ">> System packages"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip git

echo ">> NVIDIA driver (skip if already present)"
if ! command -v nvidia-smi >/dev/null 2>&1; then
  sudo apt-get install -y ubuntu-drivers-common
  sudo ubuntu-drivers autoinstall
  echo ">> Driver installed -- a reboot may be required before nvidia-smi works."
fi

echo ">> Ollama (CUDA build)"
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
sudo systemctl enable --now ollama

echo ">> Pull pinned model: $MODEL_TAG"
ollama pull "$MODEL_TAG"
ollama show "$MODEL_TAG" | sed -n '1,20p'   # record digest -> config.yaml

echo ">> Repo + venv"
[ -d MSAI-LLM-PERFORMANCE ] || git clone "$REPO_URL"
cd MSAI-LLM-PERFORMANCE
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt -r requirements-cuda.txt

echo ">> Set the cloud environment and smoke-test offline"
# flip active_environment to 'cloud' on the VM
sed -i 's/^active_environment:.*/active_environment: cloud/' config/config.yaml
./.venv/bin/python -m pytest -q

echo ">> Remote setup complete."
echo ">> On your laptop, tunnel Ollama and run against env=cloud:"
echo "     ssh -N -L 11434:localhost:11434 <user>@<vm-ip>"
