# Shadow A4500 vs Apple M5 Max — frontier-v2 comparison (analysis record)

**Generated:** 2026-07-12. Standalone record of the cross-environment comparison so it does not
have to be recomputed. Model held constant everywhere: **DeepSeek-R1-Distill-Qwen-14B, Q4_K_M**
(config hash `5031ae81369ce37b`). Sources, both committed:

- Shadow: `results/frontier-v2-shadow-trial-14b.jsonl` — env=shadow, **Ollama/CUDA**, RTX A4500, 108 rows (N=1, 3 architectures)
- M5 Max: `results/frontier-v2-calib-14b.jsonl` — env=local, **LM Studio/Metal**, fx2 subset, 310 rows

## 0. Data-coverage caveat (read first)

The M5 Max frontier-v2 file is a difficulty **calibration** run and contains **monolithic only**:

| M5 Max fx2 rows | N=1 | N=2 | N=3 | N=4 | N=5 | total |
|---|---:|---:|---:|---:|---:|---:|
| monolithic | 62 | 62 | 62 | 62 | 62 | 310 |
| agentic | 0 | 0 | 0 | 0 | 0 | **0** |
| swarm | 0 | 0 | 0 | 0 | 0 | **0** |

Therefore the **only apples-to-apples comparison is monolithic**. The Shadow trial is the **first
full 3-architecture (monolithic + agentic + swarm) frontier-v2 run on any machine** — agentic and
swarm have no M5 Max counterpart on this tier. (M5's 62 monolithic fx2 tasks are a superset of
Shadow's frozen 36-item manifest; comparison below is on the **36 shared** task IDs.)

## 1. Accuracy — monolithic, 36 shared frontier-v2 tasks, N=1

| domain | Shadow A4500 (Ollama/CUDA) | M5 Max (LM Studio/Metal) |
|--------|:--------------------------:|:------------------------:|
| math   | 3/12 | 5/12 |
| code   | 5/12 | 6/12 |
| hop    | 8/12 | 8/12 |
| **TOTAL** | **16/36 (44%)** | **19/36 (53%)** |

- **Per-cell agreement:** 25/36 = **69%** identical verdict.
- **Disagreements (11):** M5 correct where Shadow wrong = **7**; Shadow correct where M5 wrong = **4**; both correct = 12; both wrong = 13.
- **Interpretation:** a 3-item swing on 36 at N=1 is **not statistically significant**. It is also
  partly attributable to the two different model servers (Ollama vs LM Studio) serving the nominally
  identical GGUF with possibly different quant build / tokenizer / temp-0 tie-breaking — the
  documented Metal-vs-CUDA cross-environment threat (pre-reg §S12), not a capability gap.

## 2. Throughput — monolithic

| metric | Shadow A4500 (Ollama/CUDA) | M5 Max (LM Studio/Metal) |
|---|:---:|:---:|
| mean tokens/s | **36.9** | **40.4** |
| mean latency  | **73 s** | 78 s |
| n (rows) | 36 | 310 |

Effectively equal (~7% apart, latencies within ~7%). Both memory-bandwidth-bound on the ~9 GB model
(A4500 640 GB/s GDDR6; M5 Max ~400–550 GB/s unified). The A4500 is **not slow**; the earlier apparent
slowness was the orphaned-runner contention bug (trial log §3). M5 baseline-suite reference: ~50.8
tok/s (easier tasks → shorter outputs). Shadow all-108 aggregate: 37.7 tok/s (dragged down by long
agentic/swarm cells; per-call decode unchanged).

## 3. Shadow full 3-architecture results (no M5 counterpart on this tier)

| domain | monolithic | agentic | swarm |
|--------|:----------:|:-------:|:-----:|
| math   | 3/12 | 5/12 | 6/12 |
| code   | 5/12 | 2/12 | 3/12 |
| hop    | 8/12 | 7/12 | 9/12 |
| **TOTAL** | **16/36 (44%)** | **14/36 (39%)** | **18/36 (50%)** |

Directional (N=1): **swarm > monolithic > agentic**; architecture value is domain-dependent (swarm
best on every domain; agentic helps on math, hurts on execution-graded code — see trial log §6 and
`results/POST_RUN_NOTE_agentic_empty_answer.md`).

## 4. Bottom line

1. **Throughput parity confirmed:** A4500 ≈ M5 Max on this model (36.9 vs 40.4 tok/s monolithic).
2. **Monolithic accuracy 16 vs 19** — noise at N=1, plus a provider/quant component; no real gap.
3. **Only monolithic is comparable** — M5 has no agentic/swarm frontier-v2 data. To make the full
   architecture comparison cross-environment, run agentic+swarm on the M5 Max with the same manifest.
4. **Unique to Shadow:** validated CUDA/NVML telemetry (VRAM/util/power on all 108 rows), which the
   Metal path cannot provide.

## Reproduce

```bash
# survey coverage
./.venv/Scripts/python - <<'PY'
import json,collections
m5=[json.loads(l) for l in open('results/frontier-v2-calib-14b.jsonl',encoding='utf-8') if json.loads(l)['task_id'].startswith('fx2')]
bx=collections.defaultdict(collections.Counter)
for r in m5: bx[r['backend']][r['trial_idx']]+=1
print({b:dict(bx[b]) for b in bx})   # -> monolithic only
PY
```
Then compare monolithic N=1 on the 36 task IDs shared between the two files (accuracy by domain,
tokens_per_s, latency_s), as tabulated above.
