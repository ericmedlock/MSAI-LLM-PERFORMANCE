# Benchmark Analysis

- Runs: **30**  ·  Environments: **local**  ·  Model: **deepseek-r1-14b-distill-q4_k_m**
- Every metric is mean±std across trials (pre-reg S9). Pareto: minimize latency/tokens, maximize accuracy.

## By architecture

| group | n | acc | latency | tokens(tot) | actions | tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| agentic | 10 | 100% | 18.1±4.9s | 1062±40 | 2.0±0.0 | 42.9±6.4 |
| monolithic | 10 | 100% | 6.3±2.7s | 381±77 | 1.0±0.0 | 43.9±5.2 |
| swarm | 10 | 100% | 15.9±8.2s | 1364±337 | 3.0±0.0 | 60.0±7.4 |

## By architecture × task

| group | n | acc | latency | tokens(tot) | actions | tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| gsm8k-001 / agentic | 5 | 100% | 13.4±0.5s | 1024±0 | 2.0±0.0 | 48.9±1.8 |
| gsm8k-001 / monolithic | 5 | 100% | 3.8±0.3s | 308±1 | 1.0±0.0 | 48.0±3.4 |
| gsm8k-001 / swarm | 5 | 100% | 8.2±0.1s | 1044±0 | 3.0±0.0 | 66.7±1.0 |
| hotpotqa-001 / agentic | 5 | 100% | 22.8±0.2s | 1099±0 | 2.0±0.0 | 36.9±0.3 |
| hotpotqa-001 / monolithic | 5 | 100% | 8.8±0.6s | 454±0 | 1.0±0.0 | 39.9±2.8 |
| hotpotqa-001 / swarm | 5 | 100% | 23.7±1.2s | 1683±0 | 3.0±0.0 | 53.3±2.9 |

## Pareto frontiers (architecture level)

**local**

| backend | acc | latency | tokens | acc·vs·latency | acc·vs·tokens |
| --- | --- | --- | --- | --- | --- |
| agentic | 100% | 18.1s | 1062 |  |  |
| monolithic | 100% | 6.3s | 381 | ✓ | ✓ |
| swarm | 100% | 15.9s | 1364 |  |  |

## Error distribution by architecture

_No failures recorded._

