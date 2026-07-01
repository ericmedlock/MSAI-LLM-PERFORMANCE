"""The benchmark runner: tasks x backends x N trials -> telemetry rows.

Responsibilities:
- Build backends once per run from pinned config.
- For each (task, backend, trial): wrap ``backend.run`` in telemetry, grade
  the answer, and append exactly one crash-safe JSONL row.
- Be idempotent/resumable: skip run keys already present in the output file.

The runner reads which environment it represents from config, never from
code. A clock is injected so timestamps are testable and deterministic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from backends.base import Backend, Task
from backends.factory import build_backend
from backends.llm_client import LLMClient
from harness.config import Config
from harness.graders import grade
from harness.prompts import PromptSet
from harness.results import RunRecord, append_record, completed_keys
from harness.telemetry import TelemetryCollector, make_collector


@dataclass
class RunPlan:
    environment: str
    backends: list[str]
    tasks: list[Task]
    trials: int


def _now_iso(clock: Callable[[], float]) -> str:
    # local import so the module has no import-time clock dependency
    import datetime

    return datetime.datetime.fromtimestamp(clock(), datetime.timezone.utc).isoformat()


class Runner:
    def __init__(
        self,
        *,
        config: Config,
        client: LLMClient,
        prompts: PromptSet,
        collector_factory: Callable[[str], TelemetryCollector] = None,  # type: ignore[assignment]
        clock: Callable[[], float] = None,  # type: ignore[assignment]
        run_id_factory: Callable[[], str] = None,  # type: ignore[assignment]
    ) -> None:
        self._config = config
        self._client = client
        self._prompts = prompts
        self._collector_factory = collector_factory or (lambda rt: make_collector(rt))
        # injected for tests; default to wall clock / uuid in production
        import time as _time

        self._clock = clock or _time.time
        self._run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex)

    def _write_host_profile(self, env) -> tuple[str, str]:
        """Capture the static host profile once per run: write the full JSON
        sidecar, merge the normalized hosts.csv, and return (host_id, label)
        to stamp inline on every row."""
        import json
        from pathlib import Path

        from harness.hostinfo import collect_host_profile, compact_label, write_hosts_csv

        profile = collect_host_profile(
            environment=env.key,
            runtime=env.runtime,
            provider=env.provider,
            base_url=env.base_url,
            backend_model=env.model,
            judge_model=self._config.judge.model,
            config_hash=self._config.config_hash,
            timestamp=_now_iso(self._clock),
        )
        results_dir = Path(self._config.results_dir)
        out = results_dir / "host" / f"{env.key}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        write_hosts_csv([profile], results_dir / "hosts.csv")
        return profile["host_id"], compact_label(profile)

    def _build_backends(self, names: Iterable[str]) -> dict[str, Backend]:
        return {
            n: build_backend(n, client=self._client, config=self._config, prompts=self._prompts)
            for n in names
        }

    def run_plan(self, plan: RunPlan, output_path: str | Path) -> int:
        """Execute a plan, appending rows. Returns the number of NEW rows written."""
        env = self._config.env(plan.environment).resolved()
        self._host_id, self._host_label = self._write_host_profile(env)
        done = completed_keys(output_path)
        backends = self._build_backends(plan.backends)
        written = 0

        for task in plan.tasks:
            for backend_name in plan.backends:
                backend = backends[backend_name]
                for trial_idx in range(1, plan.trials + 1):
                    key = (task.task_id, backend_name, plan.environment, trial_idx)
                    if key in done:
                        continue
                    record = self._execute_one(
                        backend, task, plan.environment, env, trial_idx
                    )
                    append_record(output_path, record)
                    written += 1
        return written

    def _execute_one(
        self,
        backend: Backend,
        task: Task,
        environment: str,
        env,
        trial_idx: int,
    ) -> RunRecord:
        collector = self._collector_factory(env.runtime)
        collector.start()
        error_category: Optional[str] = None
        try:
            result = backend.run(task)
            answer = result.answer
            latency_s = result.latency_s
            tokens_in, tokens_out = result.tokens_in, result.tokens_out
            action_count = result.action_count
            metadata = result.metadata
            raw_trace = result.raw_trace
        except Exception as exc:  # a crashed backend still yields a graded row
            answer = ""
            latency_s = 0.0
            tokens_in = tokens_out = action_count = 0
            metadata = {"exception": repr(exc)}
            raw_trace = ""
            error_category = "backend_exception"
        telemetry = collector.stop()

        if error_category is None:
            correct, error_category = grade(task, answer)
        else:
            correct = False

        total_tokens = tokens_in + tokens_out
        tokens_per_s = (tokens_out / latency_s) if latency_s > 0 and tokens_out else None

        return RunRecord(
            run_id=self._run_id_factory(),
            timestamp=_now_iso(self._clock),
            backend=backend.name,
            environment=environment,
            task_id=task.task_id,
            task_domain=task.domain,
            trial_idx=trial_idx,
            model_tag=self._config.model.tag,
            config_hash=self._config.config_hash,
            provider=env.provider,
            provider_model_id=env.model,
            host_id=getattr(self, "_host_id", ""),
            host=getattr(self, "_host_label", ""),
            answer=answer,
            correct=correct,
            error_category=error_category,
            latency_s=round(latency_s, 4),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            total_tokens=total_tokens,
            tokens_per_s=round(tokens_per_s, 2) if tokens_per_s else None,
            action_count=action_count,
            telemetry=telemetry,
            metadata=metadata,
            raw_trace=raw_trace,
        )
