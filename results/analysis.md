# Benchmark Analysis

- Runs: **47**  ·  Environments: **local**  ·  Model: **deepseek-r1-14b-distill-q4_k_m**
- Every metric is mean±std across trials (pre-reg S9). Pareto: minimize latency/tokens, maximize accuracy.

## By architecture

| group | n | acc | latency | tokens(tot) | actions | tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| agentic | 16 | 81% | 51.8±72.4s | 2568±3181 | 2.4±0.8 | 42.4±5.5 |
| monolithic | 16 | 75% | 15.7±19.5s | 709±762 | 0.9±0.2 | 40.1±8.1 |
| swarm | 15 | 87% | 26.6±29.1s | 2102±1924 | 3.0±0.0 | 60.5±6.1 |

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
| humaneval-004 / agentic | 3 | 0% | 196.8±19.1s | 8978±0 | 4.0±0.0 | 41.9±4.3 |
| humaneval-004 / monolithic | 3 | 0% | 54.3±1.5s | 2227±0 | 1.0±0.0 | 37.7±1.0 |
| humaneval-004 / swarm | 2 | 0% | 96.3±1.4s | 6795±0 | 3.0±0.0 | 63.8±0.9 |

## Pareto frontiers (architecture level)

**local**

| backend | acc | latency | tokens | acc·vs·latency | acc·vs·tokens |
| --- | --- | --- | --- | --- | --- |
| agentic | 81% | 51.8s | 2568 |  |  |
| monolithic | 75% | 15.7s | 709 | ✓ | ✓ |
| swarm | 87% | 26.6s | 2102 | ✓ | ✓ |

## LLM-as-judge (secondary metric)

_Different-family judge model; quality 0–max, and agreement with the primary auto-grader._

| backend | n | quality | judge·correct | agree·w/·auto |
| --- | --- | --- | --- | --- |
| agentic | 13 | 4.00±0.00 | 100% | 100% |
| monolithic | 13 | 3.92±0.28 | 92% | 100% |
| swarm | 13 | 4.00±0.00 | 100% | 100% |

## Error distribution by architecture

| backend | backend_exception | format_error |
| --- | --- | --- |
| agentic | 0 | 3 |
| monolithic | 1 | 3 |
| swarm | 0 | 2 |
