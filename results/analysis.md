# Benchmark Analysis

- Runs: **48**  ·  Environments: **local**  ·  Model: **deepseek-r1-14b-distill-q4_k_m**
- Every metric is mean±std across trials (pre-reg S9). Pareto: minimize latency/tokens, maximize accuracy.

## By architecture

| group | n | acc | latency | tokens(tot) | actions | tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| agentic | 16 | 100% | 40.8±48.5s | 2155±2293 | 2.0±0.0 | 42.7±5.2 |
| monolithic | 16 | 94% | 18.3±25.1s | 921±1213 | 0.9±0.2 | 41.9±8.3 |
| swarm | 16 | 100% | 38.6±49.4s | 2651±2744 | 3.0±0.0 | 59.0±6.2 |

## By architecture × task

| group | n | acc | latency | tokens(tot) | actions | tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| gsm8k-001 / agentic | 5 | 100% | 13.4±0.5s | 1024±0 | 2.0±0.0 | 48.9±1.8 |
| gsm8k-001 / monolithic | 5 | 100% | 3.8±0.3s | 308±1 | 1.0±0.0 | 48.0±3.4 |
| gsm8k-001 / swarm | 5 | 100% | 8.2±0.1s | 1044±0 | 3.0±0.0 | 66.7±1.0 |
| gsm8k-004 / agentic | 3 | 100% | 19.3±1.8s | 1182±0 | 2.0±0.0 | 41.3±3.8 |
| gsm8k-004 / monolithic | 3 | 67% | 8.3±7.4s | 286±248 | 0.7±0.6 | 24.6±4.9 |
| gsm8k-004 / swarm | 3 | 100% | 15.6±0.4s | 1437±0 | 3.0±0.0 | 60.2±1.6 |
| hotpotqa-001 / agentic | 5 | 100% | 22.8±0.2s | 1099±0 | 2.0±0.0 | 36.9±0.3 |
| hotpotqa-001 / monolithic | 5 | 100% | 8.8±0.6s | 454±0 | 1.0±0.0 | 39.9±2.8 |
| hotpotqa-001 / swarm | 5 | 100% | 23.7±1.2s | 1683±0 | 3.0±0.0 | 53.3±2.9 |
| humaneval-004 / agentic | 3 | 100% | 138.2±0.7s | 6775±0 | 2.0±0.0 | 43.6±0.2 |
| humaneval-004 / monolithic | 3 | 100% | 68.5±2.0s | 3355±0 | 1.0±0.0 | 46.4±1.3 |
| humaneval-004 / swarm | 3 | 100% | 137.3±2.4s | 8157±0 | 3.0±0.0 | 54.7±1.0 |

## Pareto frontiers (architecture level)

**local**

| backend | acc | latency | tokens | acc·vs·latency | acc·vs·tokens |
| --- | --- | --- | --- | --- | --- |
| agentic | 100% | 40.8s | 2155 |  | ✓ |
| monolithic | 94% | 18.3s | 921 | ✓ | ✓ |
| swarm | 100% | 38.6s | 2651 | ✓ |  |

## LLM-as-judge (secondary metric)

_Different-family judge model; quality 0–max, and agreement with the primary auto-grader._

| backend | n | quality | judge·correct | agree·w/·auto |
| --- | --- | --- | --- | --- |
| agentic | 16 | 4.00±0.00 | 100% | 100% |
| monolithic | 16 | 3.94±0.25 | 94% | 100% |
| swarm | 16 | 4.00±0.00 | 100% | 100% |

## Error distribution by architecture

| backend | backend_exception |
| --- | --- |
| monolithic | 1 |
