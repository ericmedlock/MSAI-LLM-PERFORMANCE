#!/usr/bin/env bash
# =====================================================================
# Azure GPU VM provisioning for the CLOUD cell (C-M / C-A / C-S).
# Committed so the cloud environment is reproducible from scratch.
#
# Prereqs on your laptop: `az login` done; GPU quota approved in the target
# region (NC-series often needs a quota request on student subscriptions --
# request it EARLY, it can take a day).
#
# Usage:
#   RESOURCE_GROUP=llm-bench REGION=eastus VM_SIZE=Standard_NC4as_T4_v3 \
#     bash scripts/provision_azure.sh create      # provision + install stack
#   bash scripts/provision_azure.sh deallocate    # stop billing (keep disk)
#   bash scripts/provision_azure.sh delete        # tear everything down
#
# NOTE: values below are defaults; override via env vars. The T4 (16GB) fits
# deepseek-r1:14b Q4_K_M with headroom for 3 swarm agents. Pin ONE size for
# the whole study so cloud results are internally comparable.
# =====================================================================
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-llm-bench-rg}"
REGION="${REGION:-eastus}"
VM_NAME="${VM_NAME:-llm-bench-gpu}"
VM_SIZE="${VM_SIZE:-Standard_NC4as_T4_v3}"   # 1x NVIDIA T4, 16GB VRAM
ADMIN_USER="${ADMIN_USER:-azureuser}"
IMAGE="${IMAGE:-Canonical:ubuntu-24_04-lts:server:latest}"

cmd="${1:-create}"

create() {
  echo ">> Creating resource group $RESOURCE_GROUP in $REGION"
  az group create --name "$RESOURCE_GROUP" --location "$REGION" -o none

  echo ">> Creating VM $VM_NAME ($VM_SIZE) -- ensure GPU quota is approved"
  az vm create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --image "$IMAGE" \
    --size "$VM_SIZE" \
    --admin-username "$ADMIN_USER" \
    --generate-ssh-keys \
    --public-ip-sku Standard \
    -o none

  echo ">> Opening no extra ports (Ollama is reached over SSH tunnel, not exposed)"
  ip=$(az vm show -d -g "$RESOURCE_GROUP" -n "$VM_NAME" --query publicIps -o tsv)
  echo ">> VM public IP: $ip"
  echo ">> Now run the remote setup:"
  echo "     ssh ${ADMIN_USER}@${ip} 'bash -s' < scripts/setup_remote.sh"
  echo ">> Then tunnel Ollama:  ssh -N -L 11434:localhost:11434 ${ADMIN_USER}@${ip}"
}

deallocate() {
  echo ">> Deallocating $VM_NAME (stops GPU billing; keeps disk)"
  az vm deallocate --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" -o none
}

delete() {
  echo ">> Deleting resource group $RESOURCE_GROUP (irreversible)"
  az group delete --name "$RESOURCE_GROUP" --yes --no-wait
}

case "$cmd" in
  create) create ;;
  deallocate) deallocate ;;
  delete) delete ;;
  *) echo "usage: $0 {create|deallocate|delete}" >&2; exit 2 ;;
esac
