#!/bin/bash
# Model-server bootstrap: installs Ollama if missing (root NOT required on
# Linux), starts it, pulls the requested model. Git Bash / Linux / macOS.
# Called by scripts/setup.sh; safe to run standalone or repeatedly.
#
# Usage: bash scripts/bootstrap_model_server.sh [model_tag]   (default deepseek-r1:14b)
set -euo pipefail
MODEL="${1:-deepseek-r1:14b}"
BASE="${OLLAMA_BASE:-http://localhost:11434}"
USERBIN="$HOME/.local/bin"
# OLLAMA_VERSION (optional): exact release for the Linux no-root install.
# Defaults to v0.24.0 — the version serving the pinned local (M5 Max) cell —
# so every environment runs the same server build unless deliberately overridden.
# OLLAMA_MODELS (optional): model cache dir; on HPC point at scratch, not $HOME.

have() { command -v "$1" >/dev/null 2>&1; }

if [ -n "${OLLAMA_MODELS:-}" ]; then
  mkdir -p "$OLLAMA_MODELS"
  echo "[bootstrap] model cache: $OLLAMA_MODELS"
fi

# --- 1. install ollama if missing ------------------------------------------------
if ! have ollama; then
  echo "[bootstrap] ollama not found — installing"
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)   # Windows Git Bash
      if have winget; then
        winget install --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
        export PATH="$PATH:$LOCALAPPDATA/Programs/Ollama"
      else
        echo "[bootstrap] winget unavailable — install manually: https://ollama.com/download/windows"; exit 1
      fi
      ;;
    Linux)
      # No-root install (HPC-friendly) from the official GitHub release.
      # (ollama.com/download/ollama-linux-amd64.tgz is gone — 404 as of
      # 2026-07-13; releases now ship .tar.zst with a sha256sum.txt.)
      OLLAMA_VERSION="${OLLAMA_VERSION:-v0.24.0}"
      have zstd || { echo "[bootstrap] FATAL: zstd not found (tar needs it). Try: module load zstd"; exit 1; }
      REL="https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}"
      TMPD="$(mktemp -d)"
      echo "[bootstrap] downloading ollama ${OLLAMA_VERSION} (pinned, no root needed)"
      curl -fsSL -o "$TMPD/ollama-linux-amd64.tar.zst" "$REL/ollama-linux-amd64.tar.zst"
      curl -fsSL -o "$TMPD/sha256sum.txt" "$REL/sha256sum.txt"
      (cd "$TMPD" && grep ' \./ollama-linux-amd64\.tar\.zst$' sha256sum.txt | sha256sum -c -) \
        || { echo "[bootstrap] FATAL: checksum mismatch on ollama tarball"; exit 1; }
      mkdir -p "$USERBIN"
      tar --zstd -xf "$TMPD/ollama-linux-amd64.tar.zst" -C "$HOME/.local"
      rm -rf "$TMPD"
      export PATH="$USERBIN:$PATH"
      ;;
    Darwin)
      if have brew; then brew install ollama; else echo "install from https://ollama.com/download/mac"; exit 1; fi
      ;;
  esac
fi
have ollama || { echo "[bootstrap] ollama still not on PATH — open a fresh shell and re-run"; exit 1; }

# --- 2. make sure the server is up -----------------------------------------------
# Server flags (A/B-tested 2026-07-11, outputs byte-identical to pure defaults):
#   KEEP_ALIVE=-1     never unload the model mid-session (prevents reload stalls)
#   NUM_PARALLEL=1    runs are strictly sequential; parallel slots just partition KV
# OLLAMA_FLASH_ATTENTION was tested and REJECTED: -3.8% aggregate on Metal
# (-5..8% on long generations); see vault Engineering Log E11.
if ! curl -sf "$BASE/api/tags" >/dev/null; then
  echo "[bootstrap] starting ollama serve"
  (OLLAMA_HOST="${BASE#http://}" OLLAMA_KEEP_ALIVE=-1 OLLAMA_NUM_PARALLEL=1 ollama serve >/dev/null 2>&1 &)
  for i in $(seq 1 30); do curl -sf "$BASE/api/tags" >/dev/null && break; sleep 2; done
fi
curl -sf "$BASE/api/tags" >/dev/null || { echo "[bootstrap] ollama server did not come up"; exit 1; }

# --- 3. pull the model (skipped when already cached, so this step is offline-safe
# --- on cluster compute nodes; a cache miss there fails loudly with a remedy) ------
if curl -sf "$BASE/api/tags" | grep -q "\"name\":\"$MODEL\""; then
  echo "[bootstrap] $MODEL already cached — skipping pull"
else
  echo "[bootstrap] pulling $MODEL"
  ollama pull "$MODEL" || {
    echo "[bootstrap] FATAL: pull failed. If this node has no internet, pre-stage the"
    echo "[bootstrap] model from a login node: bash scripts/setup.sh --download"
    exit 1
  }
fi

# --- 4. GPU sanity ----------------------------------------------------------------
if have nvidia-smi; then
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
elif [ "$(uname -s)" = "Darwin" ]; then
  echo "[bootstrap] Apple Silicon (Metal) — NVML telemetry not applicable"
else
  echo "[bootstrap] WARNING: nvidia-smi not found — CUDA telemetry (pynvml) will be empty"
fi
echo "[bootstrap] ready: $BASE serving $MODEL (ollama $(ollama --version 2>/dev/null | grep -o '[0-9][0-9.]*' | head -1 || echo '?'))"
