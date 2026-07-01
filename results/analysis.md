# Benchmark Analysis

- Runs: **225**  ·  Environments: **local**  ·  Model: **deepseek-r1-14b-distill-q4_k_m**
- Host (`local`): **Apple M5 Max**, 48 GB RAM (unified/VRAM 48 GB), macOS-26.5.1-arm64-arm-64bit-Mach-O · serving openai `deepseek-r1-distill-qwen-14b`
- Every metric is mean±std across trials (pre-reg S9). Pareto: minimize latency/tokens, maximize accuracy.

## By architecture

| group | n | acc | latency | tokens(tot) | actions | tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| agentic | 75 | 100% | 32.5±32.0s | 1961±1662 | 2.1±0.5 | 44.5±4.1 |
| monolithic | 75 | 93% | 15.2±17.5s | 832±850 | 1.0±0.0 | 44.9±5.4 |
| swarm | 75 | 93% | 32.9±33.1s | 2649±2247 | 3.0±0.0 | 63.0±4.9 |

## By architecture × task

| group | n | acc | latency | tokens(tot) | actions | tok/s |
| --- | --- | --- | --- | --- | --- | --- |
| gsm8k-001 / agentic | 5 | 100% | 15.3±0.7s | 1024±0 | 2.0±0.0 | 42.9±2.1 |
| gsm8k-001 / monolithic | 5 | 100% | 5.4±4.1s | 308±1 | 1.0±0.0 | 42.7±16.0 |
| gsm8k-001 / swarm | 5 | 100% | 10.3±1.1s | 1044±0 | 3.0±0.0 | 53.7±5.1 |
| gsm8k-002 / agentic | 5 | 100% | 14.1±0.3s | 782±0 | 2.0±0.0 | 35.2±0.8 |
| gsm8k-002 / monolithic | 5 | 100% | 6.8±0.1s | 370±0 | 1.0±0.0 | 36.7±0.3 |
| gsm8k-002 / swarm | 5 | 100% | 11.0±0.4s | 1092±0 | 3.0±0.0 | 56.5±1.9 |
| gsm8k-003 / agentic | 5 | 100% | 15.4±0.9s | 1067±0 | 2.0±0.0 | 37.4±2.3 |
| gsm8k-003 / monolithic | 5 | 100% | 4.6±0.1s | 321±0 | 1.0±0.0 | 37.4±0.5 |
| gsm8k-003 / swarm | 5 | 100% | 17.6±0.4s | 1599±0 | 3.0±0.0 | 58.7±1.3 |
| gsm8k-004 / agentic | 5 | 100% | 16.4±0.3s | 1182±0 | 2.0±0.0 | 48.2±1.0 |
| gsm8k-004 / monolithic | 5 | 100% | 6.2±0.1s | 429±0 | 1.0±0.0 | 48.6±0.8 |
| gsm8k-004 / swarm | 5 | 100% | 14.2±0.2s | 1437±0 | 3.0±0.0 | 65.8±1.1 |
| gsm8k-005 / agentic | 5 | 100% | 17.3±0.6s | 1185±0 | 2.0±0.0 | 47.3±1.6 |
| gsm8k-005 / monolithic | 5 | 100% | 6.1±0.1s | 403±0 | 1.0±0.0 | 47.1±0.7 |
| gsm8k-005 / swarm | 5 | 100% | 15.2±0.3s | 1470±0 | 3.0±0.0 | 66.2±1.2 |
| hotpotqa-001 / agentic | 5 | 100% | 19.2±0.3s | 1099±0 | 2.0±0.0 | 43.8±0.7 |
| hotpotqa-001 / monolithic | 5 | 100% | 7.9±0.1s | 454±0 | 1.0±0.0 | 44.4±0.5 |
| hotpotqa-001 / swarm | 5 | 100% | 20.0±0.4s | 1683±0 | 3.0±0.0 | 63.0±1.1 |
| hotpotqa-002 / agentic | 5 | 100% | 32.0±0.4s | 1959±0 | 4.0±0.0 | 43.0±0.5 |
| hotpotqa-002 / monolithic | 5 | 0% | 5.1±0.1s | 333±0 | 1.0±0.0 | 44.0±0.6 |
| hotpotqa-002 / swarm | 5 | 0% | 14.3±0.3s | 1251±0 | 3.0±0.0 | 56.7±1.1 |
| hotpotqa-003 / agentic | 5 | 100% | 12.6±0.2s | 816±0 | 2.0±0.0 | 43.6±0.8 |
| hotpotqa-003 / monolithic | 5 | 100% | 6.9±0.4s | 409±0 | 1.0±0.0 | 44.4±2.4 |
| hotpotqa-003 / swarm | 5 | 100% | 12.0±0.9s | 1182±0 | 3.0±0.0 | 63.3±4.3 |
| hotpotqa-004 / agentic | 5 | 100% | 10.0±0.3s | 751±0 | 2.0±0.0 | 48.4±1.5 |
| hotpotqa-004 / monolithic | 5 | 100% | 5.7±0.2s | 383±4 | 1.0±0.0 | 48.5±1.2 |
| hotpotqa-004 / swarm | 5 | 100% | 11.5±0.4s | 1194±0 | 3.0±0.0 | 66.8±2.5 |
| hotpotqa-005 / agentic | 5 | 100% | 11.6±0.2s | 824±0 | 2.0±0.0 | 48.6±1.0 |
| hotpotqa-005 / monolithic | 5 | 100% | 3.2±0.1s | 262±0 | 1.0±0.0 | 49.1±1.0 |
| hotpotqa-005 / swarm | 5 | 100% | 14.8±0.7s | 1429±34 | 3.0±0.0 | 67.8±1.8 |
| humaneval-001 / agentic | 5 | 100% | 80.1±1.5s | 4443±4 | 2.0±0.0 | 43.5±0.8 |
| humaneval-001 / monolithic | 5 | 100% | 42.6±1.0s | 2050±0 | 1.0±0.0 | 42.8±1.0 |
| humaneval-001 / swarm | 5 | 100% | 82.1±2.9s | 6228±141 | 3.0±0.0 | 66.3±0.9 |
| humaneval-002 / agentic | 5 | 100% | 53.4±0.4s | 3355±0 | 2.0±0.0 | 48.7±0.4 |
| humaneval-002 / monolithic | 5 | 100% | 28.2±0.3s | 1568±3 | 1.0±0.0 | 49.4±0.5 |
| humaneval-002 / swarm | 5 | 100% | 82.4±1.7s | 6240±61 | 3.0±0.0 | 68.1±0.9 |
| humaneval-003 / agentic | 5 | 100% | 22.2±1.0s | 1596±0 | 2.0±0.0 | 43.1±1.9 |
| humaneval-003 / monolithic | 5 | 100% | 12.1±0.3s | 689±0 | 1.0±0.0 | 44.0±1.1 |
| humaneval-003 / swarm | 5 | 100% | 21.2±0.4s | 1935±0 | 3.0±0.0 | 63.5±1.0 |
| humaneval-004 / agentic | 5 | 100% | 129.6±0.5s | 6775±0 | 2.0±0.0 | 46.5±0.2 |
| humaneval-004 / monolithic | 5 | 100% | 66.9±2.1s | 3355±0 | 1.0±0.0 | 47.5±1.4 |
| humaneval-004 / swarm | 5 | 100% | 118.2±7.6s | 8061±131 | 3.0±0.0 | 62.9±3.5 |
| humaneval-005 / agentic | 5 | 100% | 37.5±1.1s | 2561±0 | 2.0±0.0 | 47.2±1.4 |
| humaneval-005 / monolithic | 5 | 100% | 20.7±0.6s | 1140±0 | 1.0±0.0 | 46.7±1.3 |
| humaneval-005 / swarm | 5 | 100% | 49.3±0.8s | 3895±20 | 3.0±0.0 | 66.1±0.9 |

## Pareto frontiers (architecture level)

**local**

| backend | acc | latency | tokens | acc·vs·latency | acc·vs·tokens |
| --- | --- | --- | --- | --- | --- |
| agentic | 100% | 32.5s | 1961 | ✓ | ✓ |
| monolithic | 93% | 15.2s | 832 | ✓ | ✓ |
| swarm | 93% | 32.9s | 2649 |  |  |

## LLM-as-judge (secondary metric)

_Different-family judge model; quality 0–max, and agreement with the primary auto-grader._

| backend | n | quality | judge·correct | agree·w/·auto |
| --- | --- | --- | --- | --- |
| agentic | 70 | 3.79±0.78 | 93% | 93% |
| monolithic | 70 | 3.71±1.04 | 93% | 100% |
| swarm | 71 | 3.79±0.77 | 93% | 100% |

## Error distribution by architecture

| backend | reasoning_error |
| --- | --- |
| monolithic | 5 |
| swarm | 5 |
