# HPC Self-Containment — Design Document (first pass)

**Branch:** `hpc` · **Status:** DESIGN ONLY — nothing here is implemented yet
**Goal:** run the frozen frontier-v2 sweeps on the UNCC research cluster with
(1) a simple one-time setup, (2) an interactive **`startup.sh`** that asks for
parameters with sensible defaults, and (3) fully unattended, self-contained,
resumable execution — no babysitting, no internet assumptions, no root.

---

## 1. Goals and non-goals

**Goals**

- G1. One entry point: `bash scripts/startup.sh` — interactive wizard *or* fully
  scripted via flags/env (CI-style), with defaults for everything.
- G2. Self-contained on a cluster: works with no root, no systemd, no internet on
  compute nodes, home-directory quotas, shared filesystems, SLURM scheduling.
- G3. Reproducible & provenanced: pinned server version, pinned model artifacts
  (digest-verified), every run bundle recorded.
- G4. Zero changes to frozen science: `config/config.yaml`, `tasks/*`, `prompts/*`
  stay byte-identical (config bytes are hashed into every row). Everything below is
  **additive** (new files, new scripts).

**Non-goals**

- Multi-node distributed inference (one model server per job/GPU is enough).
- Kubernetes/cloud portability (Azure cell already has its own scripts).
- Replacing the Shadow/local flows — `startup.sh` wraps the same underlying
  `setup.sh`/`run_trials.sh` so every environment keeps one code path.

---

## 2. Current state (what already exists on this branch)

| Piece | Does today | Cluster gap |
|---|---|---|
| `scripts/setup.sh` | venv + deps + offline tests + Ollama bootstrap (no-root tarball) + model pull | assumes internet at run time; installs to `~/.local`; latest-Ollama (unpinned); single monolithic phase |
| `scripts/run_trials.sh` | profile-aware (shadow/hpc/local), env-var overrides, resumable | fixed port 11434 (collides when 2 jobs share a node); no params file; server lifecycle not owned per-job |
| `docs/HPC_RUNBOOK.md` | manual SLURM template to copy-paste | human copies/edits by hand; nothing generated or recorded |
| `config.yaml` `hpc` env | provider=ollama @ localhost:11434 | base_url must become per-job dynamic (via `LLM_BASE_URL` override — mechanism already exists) |
| Harness | idempotent runner, row checkpointing, host provenance, judge, analyze | nothing — this layer is cluster-ready as-is |
| `.claude/skills/run-trials` | drives setup+run on any box | should learn the `startup.sh` vocabulary (optional on cluster — login nodes may not have Claude Code) |

---

## 3. Component designs

### D1 — `scripts/startup.sh` (the new entry point)

A thin, dependency-free bash wizard. **Interactive when on a TTY, fully
non-interactive with `--yes`** (accept all defaults) or explicit flags. Every
prompt shows its default; Enter accepts.

```
Usage:
  bash scripts/startup.sh                    # wizard
  bash scripts/startup.sh --yes              # all defaults, no questions
  bash scripts/startup.sh --stage confirm --submit          # scripted
  bash scripts/startup.sh status|judge|analyze|resume       # subcommands
```

**Prompt flow (wizard mode), in order, with defaults:**

| # | Prompt | Default | Notes / validation |
|---|---|---|---|
| 1 | Run stage? `trial` / `confirm` / `scale-32b` / `scale-qwen` / `custom` | `confirm` | sets 2–6 automatically; `custom` unlocks each |
| 2 | Model (Ollama tag) | stage-dependent (`deepseek-r1:14b`) | free text on `custom` |
| 3 | Trials N | stage-dependent (5 confirm / 1 trial / 2 scaling) | integer 1–10 |
| 4 | Backends | `monolithic agentic swarm` | subset validation |
| 5 | Output file | stage-dependent (`results/frontier-v2-hpc-14b.jsonl`) | refuses an existing file bound to a *different* model tag |
| 6 | Execution mode? `sbatch` / `now` / `print` | `sbatch` if `sbatch` on PATH, else `now` | `print` = generate everything, submit nothing |
| 7 | SLURM: partition | `$HPC_PARTITION` or `GPU` | only asked in sbatch mode; remembered (see D5 site file) |
| 8 | SLURM: gres/GPU | `gpu:1` | " |
| 9 | SLURM: walltime | `24:00:00` | " |
| 10 | SLURM: account | (empty = omit) | " |
| 11 | Scratch dir (venv+models live here) | `$SCRATCH` else `$HOME/scratch` else repo dir | quota warning if under `$HOME` |
| 12 | Email on end/fail | (empty = none) | `#SBATCH --mail-*` |

Then prints a **summary block** and asks `Proceed? [Y/n]`.

**What it generates (the "run bundle")** — `runs/<UTCstamp>-<stage>/`:

- `params.env` — every answer as `KEY=value` (the single source the other scripts read)
- `job.sbatch` — generated from a template, embedding `params.env` by path
- `submit.log` — job id, timestamps (appended on submit/resume)

Bundles are **committed** (tiny, pure provenance); a `runs/.gitignore` excludes
logs over a size cap. `resume` re-submits the newest (or named) bundle unchanged.

**Subcommands:**

- `status` — `squeue` for our job ids + `wc -l` per output file vs. expected cells
  + last row's timestamp (staleness check)
- `judge` / `analyze` — run post-processing over `results/frontier-v2-*.jsonl`
  (login node OK — judge needs the Ollama server, so `judge` reuses D3 lifecycle)
- `resume` — resubmit newest bundle (idempotence makes this always safe)

**Site memory:** first successful wizard writes `~/.config/msai-llm/site.env`
(partition, account, scratch) so later runs default to the previous answers.

### D2 — `setup.sh`: split into online/offline stages

Cluster compute nodes frequently have **no internet**. Split:

- `setup.sh --download` (login node, internet): venv build + pip install, download
  **pinned** Ollama tarball, `ollama pull` each needed model into
  `$SCRATCH/ollama-models` (`OLLAMA_MODELS`), then **digest-verify** (D4).
- `setup.sh --offline` (compute node): PATH/env assembly + sanity checks only —
  fails fast with a named remedy if any artifact is missing.
- Plain `setup.sh` (no flag) = current behavior (download+verify+ready) for
  laptop/Shadow, so existing docs/skill stay true.

**Pinning:** `OLLAMA_VERSION` (exact release, e.g. `v0.9.x`) hardcoded with the
tarball URL + sha256 in D4's lock file. Today's "latest" is a reproducibility hole.

### D3 — `run_trials.sh`: per-job server lifecycle + port isolation

- **Dynamic port:** `PORT=$((20000 + ${SLURM_JOB_ID:-$$} % 20000))`, retry-scan if
  busy. Export `LLM_BASE_URL=http://127.0.0.1:$PORT` (existing env-override
  mechanism — **no config.yaml change**). `OLLAMA_HOST=127.0.0.1:$PORT` for the server.
- **Own the server:** start `ollama serve` in-job, health-poll, `trap` kill on
  exit — nothing leaks past the job. `OLLAMA_MODELS=$SCRATCH/...` (read-only reuse
  of the login-node pull; Ollama supports concurrent readers).
- **Params file:** `run_trials.sh --params runs/<bundle>/params.env` becomes the
  primary invocation (generated jobs use it); positional profile mode stays for
  humans.
- **Guard:** refuse to start if the output file's last row's `model_tag` differs
  from the requested tag (prevents the one unrecoverable mistake: two models in
  one JSONL).

### D4 — `config/artifacts.lock.json` (new, additive)

```json
{
  "ollama":  { "version": "vX.Y.Z", "linux-amd64.tgz.sha256": "..." },
  "models": {
    "deepseek-r1:14b":  { "expected_digest": "sha256:..." },
    "deepseek-r1:32b":  { "expected_digest": "sha256:..." },
    "qwen3.6-35b-a3b":  { "expected_digest": "sha256:..." }
  }
}
```

Digests captured once (from the already-pulled M5 Max copies / first login-node
pull) and verified by `setup.sh --download` and at job start. Extends the
config.yaml `model.digest` idea to every artifact **without touching config.yaml**.

### D5 — SLURM template (`scripts/templates/job.sbatch.in`)

Placeholder-substituted by `startup.sh` (no heredocs in the wizard):

```
#SBATCH -J {{JOB_NAME}}          — msai-<stage>
#SBATCH --partition {{PARTITION}}
#SBATCH --gres {{GRES}}          — gpu:1
#SBATCH --mem 32G  --time {{WALLTIME}}
#SBATCH --requeue                — safe: row-level resumability
{{#ACCOUNT}}#SBATCH -A {{ACCOUNT}}{{/ACCOUNT}}
{{#MAIL}}#SBATCH --mail-type=END,FAIL --mail-user={{MAIL}}{{/MAIL}}
#SBATCH -o runs/{{BUNDLE}}/slurm-%j.out

cd $SLURM_SUBMIT_DIR
bash scripts/setup.sh --offline
bash scripts/run_trials.sh --params runs/{{BUNDLE}}/params.env
```

Notes: 14B ≈ 10 GB VRAM, 32B ≈ 20 GB (fits any modern data-center GPU);
`--requeue` + idempotent runner = timeout-proof; one output file per job, never
shared. Whether `module load cuda` is needed is a site unknown (§5) — template
gets an optional `{{MODULES}}` line.

### D6 — Provenance additions

- Run bundle (D1) captures every parameter + job id + submit time.
- Job start appends to the bundle: node name, `nvidia-smi` line, Ollama version,
  model digest actually served (from `ollama show`).
- Existing per-row host stamping already records hardware per row — unchanged.
- After data lands: results JSONL + `results/host/hpc.json` + the bundle are
  committed together (same rule as Shadow).

### D7 — Docs & skill

- `docs/HPC_RUNBOOK.md`: rewritten around `startup.sh` (wizard transcript with
  screenshots-in-text, then the scripted one-liner); manual template demoted to
  appendix.
- `.claude/skills/run-trials`: add the `startup.sh` vocabulary and the split-stage
  rule ("on a cluster: `--download` on login node, jobs do `--offline`"); note
  Claude Code is optional on the cluster — `startup.sh` is the no-Claude path.
- Shadow guide: unaffected (plain `setup.sh` keeps its behavior).

---

## 4. What deliberately does NOT change

`config/config.yaml` (bytes hashed into `config_hash`), `tasks/*` (frozen),
`prompts/*` (frozen), the harness runner/grader/judge (cluster-ready), the
pre-registration (compute environments don't touch study cells; `hpc` env block
already exists and was amendment-noted).

---

## 5. Site unknowns — answers needed before implementation hardening

Collected by the wizard with defaults, but confirm once (cluster docs or a
5-minute login-node session):

| # | Question | Default assumption | Risk if wrong |
|---|---|---|---|
| U1 | Partition name(s) for GPU jobs | `GPU` | job rejected at submit (cheap fix) |
| U2 | Account/allocation string required? | none | submit rejection |
| U3 | Internet on compute nodes? | **no** (design assumes worst case) | none — design covers both |
| U4 | Internet on login nodes? | yes | if also no: pre-stage artifacts from laptop via `scp` (documented fallback) |
| U5 | Scratch path convention | `$SCRATCH` | home-quota exhaustion (venv+models ≈ 15–35 GB) |
| U6 | Module system needed for GPU driver visibility? | not needed (Ollama bundles CUDA libs; driver comes from node) | server falls back to CPU — caught by D6 start-check + telemetry check |
| U7 | Max walltime / requeue policy | 24 h, requeue allowed | longer sweeps split across resubmits (safe, just slower) |
| U8 | `ssh` to compute nodes allowed (for live debugging)? | no | debugging via slurm-out files only |

---

## 6. Implementation order (each step independently testable)

1. **D4 lock file** + digest capture from existing local artifacts (no behavior change)
2. **D2 setup split** (`--download`/`--offline`; default path unchanged) — testable on the M5 Max
3. **D3 run_trials lifecycle** (port isolation + params file + model-tag guard) — testable locally by running two instances
4. **D5 template + D1 startup.sh** (wizard, bundle, submit/status/resume) — `print` mode testable anywhere; `sbatch` path validated on the cluster
5. **D7 docs + skill** update
6. **Dry-run on the real cluster**: `--download` on login node → 1-task smoke job (`--backend monolithic TRIALS=1` on 1 item via `MANIFEST` narrowing… simplest: `--print` then a 15-min job) → then the confirmatory submit

Estimated effort: steps 1–3 ≈ one session; 4 ≈ one session; 5–6 ≈ an hour plus
cluster wait times.

---

## 7. Risks / open design questions

- **R1. Ollama GPU libs vs. very old cluster drivers** — if the node driver is too
  old for the pinned Ollama, fallback is llama.cpp `llama-server` built on the
  login node (kept as a documented escape hatch, not a maintained path).
- **R2. Judge on cluster vs. laptop** — judge needs a served Llama-3.2-3B. Design
  choice: judge runs *wherever* `startup.sh judge` is invoked (it owns a server
  either way); default remains the laptop to keep cluster jobs single-purpose.
- **R3. Two jobs, one bundle** — `resume` resubmits the same output file; guard
  D3 makes double-running merely wasteful (idempotent skip), not corrupting; a
  `squeue` check in `resume` warns if the bundle's job id is still queued/running.
- **R4. Windows Git Bash regression** — D2/D3 refactors must keep the Shadow path
  green; the offline test suite plus a Shadow re-run of `setup.sh` is the gate.
- **Q1. Should scaling legs (32B/qwen) run at N=2 or N=5?** Design assumes N=2
  (exploratory; pre-registered N=5 applies to the pinned-14B confirmatory only).
- **Q2. Commit run bundles — always, or only successful ones?** Design says always
  (failed submits are provenance too); revisit if noise accumulates.
