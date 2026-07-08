"""Benchmark harness package.

Silence a noisy third-party pending-deprecation warning emitted by LangGraph
at import time so CLI/telemetry output stays clean. This affects only
warning display, not behavior.
"""

import warnings

warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects` will change",
    category=Warning,
)
