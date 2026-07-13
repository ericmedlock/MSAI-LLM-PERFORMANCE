# Azure cloud cell (C-M / C-A / C-S) — laptop-driven runbook

> **SUPERSEDED (2026-07-13):** the Azure phase now uses **managed AI services (Azure AI
> Foundry)** instead of a GPU VM — see `docs/AZURE_FOUNDRY_PHASE.md`. This runbook is
> retained as the fallback if artifact parity in the cloud is ever required.

The pre-registered **cloud** environment (§7). The harness runs **on the Azure GPU VM** so
`pynvml` telemetry is GPU-local (VRAM/util/power) — the same reason the Shadow trial existed.
Drive everything from your **laptop**; the long run executes on the VM detached, so your laptop
can disconnect without killing it. Same pinned model/config as every other cell
(`deepseek-r1:14b`, Q4_K_M, config hash stamped per row).

> **Cost discipline (read once):** a GPU VM bills per hour while *allocated*. Always
> `deallocate` when idle and `delete` when done. A full N=5 cloud cell (540 runs) on a T4 is
> ~30–40 h ≈ **$15–30 on-demand**. Pilot first.

---

## Step 0 — Laptop prereqs (you)

```bash
# Azure CLI
#   macOS:  brew install azure-cli
#   Windows: winget install -e --id Microsoft.AzureCLI
az login                     # opens a browser — this is the step Claude cannot do for you
az account show -o table     # confirm the right subscription is active
# if not: az account set --subscription "<name-or-id>"
```

## Step 1 — GPU quota (CURRENT BLOCKER — do this first)

The default VM is `Standard_NC4as_T4_v3` (1× T4 16 GB), in the **NCASv3_T4** family, needs **4 vCPU**.
On student/free subs this quota is often **0** and approval can take ~a day — request early.

```bash
# check current NC-family quota/usage in the target region
az vm list-usage --location eastus -o table | grep -i "NC"
```

- If the **NCASv3_T4 Family** limit is ≥ 4 → you're good, go to Step 2.
- If it's 0 / too low → request an increase:
  **Azure Portal → Subscriptions → your sub → Usage + quotas → search "NCASv3_T4" →
  Request increase → set limit to at least 4 (8 gives headroom).**
  (CLI alternative: `az quota` — the portal is more reliable for GPU families.)
- Different region if eastus is constrained: try `eastus2`, `southcentralus`, `westus2`
  (re-check quota per region; keep ONE region for the whole cloud cell).

**Tell Claude the quota result** and we continue.

## Step 2 — Provision the VM (once quota is approved)

```bash
cd ~/…/MSAI-LLM-PERFORMANCE
git pull        # ensure latest main (client thinking-field fix + CUDA telemetry deps)

RESOURCE_GROUP=llm-bench-rg REGION=eastus VM_SIZE=Standard_NC4as_T4_v3 \
  bash scripts/provision_azure.sh create
# prints the VM public IP and the exact next command
```

## Step 3 — Install the stack on the VM

```bash
ssh azureuser@<vm-ip> 'bash -s' < scripts/setup_remote.sh
```
This installs the NVIDIA driver, Ollama (CUDA), clones the repo fresh from `main`, builds the venv
with `requirements.txt + requirements-cuda.txt` (so `pynvml` telemetry works), pulls the pinned
model, and flips `active_environment: cloud`. **If it says a reboot is needed for the driver:**
`az vm restart -g llm-bench-rg -n llm-bench-gpu`, then re-run the ssh line (idempotent).

Verify the GPU on the VM before spending anything:
```bash
ssh azureuser@<vm-ip> 'nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
# expect: Tesla T4, 15360 MiB (or 16384)
```

## Step 4 — PILOT: 1 task × 3 architectures, ON THE VM (telemetry check)

Run on the VM (not over a tunnel) so `pynvml` is GPU-local. One task, all 3 backends, N=1:

```bash
ssh azureuser@<vm-ip>
cd MSAI-LLM-PERFORMANCE
OUT=results/azure-pilot.jsonl TRIALS=1 \
  bash scripts/run_trials.sh --manifest tasks/frontier_v2_manifest.json --task-id fx2-mathA-001
# (run_trials auto-detects the VM as a CUDA profile; env=cloud from config)
```
**The point of the pilot** — confirm cloud telemetry is non-zero:
```bash
head -n1 results/azure-pilot.jsonl | ./.venv/bin/python -m json.tool | grep -iE "vram|gpu|power"
# expect peak_vram_mb / avg_gpu_util_pct / gpu_power_w all NON-null
```
If null → stop and tell Claude (check `ollama ps` shows 100% GPU; `pynvml` installed). If good →
note the T4's tok/s and decide scale.

## Step 5 — Full cloud cell: N=5, all 3 architectures, detached on the VM

Run under `tmux` (or `nohup`) so it survives your SSH/laptop disconnecting:
```bash
ssh azureuser@<vm-ip>
cd MSAI-LLM-PERFORMANCE
tmux new -s cloud
TRIALS=5 OUT=results/frontier-v2-cloud-n5-14b.jsonl bash scripts/run_trials.sh
# detach: Ctrl-b then d   |   reattach later: tmux attach -t cloud
```
540 runs, row-level checkpointed (resumable). Check progress anytime:
`ssh azureuser@<vm-ip> 'wc -l MSAI-LLM-PERFORMANCE/results/frontier-v2-cloud-n5-14b.jsonl'`.

## Step 6 — Bring results home + commit

```bash
scp azureuser@<vm-ip>:MSAI-LLM-PERFORMANCE/results/frontier-v2-cloud-n5-14b.jsonl results/
scp azureuser@<vm-ip>:MSAI-LLM-PERFORMANCE/results/host/cloud.json results/host/ 2>/dev/null || true
git add results/frontier-v2-cloud-n5-14b.jsonl results/host/cloud.json
git commit -m "data(cloud): frontier-v2 N=5, Azure T4 (CUDA)"
git push
```

## Step 7 — STOP BILLING (do not skip)

```bash
bash scripts/provision_azure.sh deallocate   # between sessions (keeps disk, stops GPU billing)
bash scripts/provision_azure.sh delete        # when fully done (tears down the resource group)
```

---

### Notes
- **Record the model digest** the VM pulled (`ollama show deepseek-r1:14b`) and confirm it matches
  `config.yaml model.digest`; if it differs, flag it — cross-environment digest parity is a
  reproducibility invariant.
- **Why on-VM, not tunnel:** the committed scripts mention an Ollama SSH tunnel for convenience, but
  running the harness on your laptop would capture *laptop* telemetry (no GPU → null). Always run the
  data-collection command on the VM.
- This cell + HPC (N=5) + the M5 Max architectures (see `M5_MAX_N5_RUNBOOK.md`) complete the
  pre-registered environment × architecture matrix.
