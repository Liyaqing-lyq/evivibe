"""Task runner interface: executes standard user tasks against a work.

A *standard user task* is a scripted end-to-end interaction (open app, login,
create / edit / search / delete data, reload, verify persistence, abnormal
inputs).  Runners produce TaskResults plus Evidence (logs, step outcomes,
screenshots) that reviewers must cite.

Two implementations are provided:

* :class:`ReplayRunner` -- deterministic replay of a recorded runtime trace
  (``runtime_trace.json``).  This makes offline evaluation and CI exactly
  reproducible, and is how the benchmark ships without live services.
* :class:`PlaywrightRunner` -- live execution in a real browser (optional
  dependency ``playwright``).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..schema import Evidence, StepResult, TaskResult

REQUIRED_TASK_FIELDS = {"task_id", "name", "category", "steps"}


def validate_tasks(tasks: List[Dict]) -> List[Dict]:
    """Basic structural validation of the task specification."""
    seen = set()
    for t in tasks:
        missing = REQUIRED_TASK_FIELDS - set(t)
        if missing:
            raise ValueError(
                f"task {t.get('task_id', '?')} missing fields: {missing}")
        if t["task_id"] in seen:
            raise ValueError(f"duplicate task_id: {t['task_id']}")
        seen.add(t["task_id"])
    return tasks


class BaseRunner:
    """Executes tasks and collects evidence."""

    name = "base"

    def run(self, work, tasks: List[Dict]) -> Tuple[List[TaskResult], List[Evidence]]:
        raise NotImplementedError

    # -- shared helpers ------------------------------------------------------

    @staticmethod
    def _step_results(spec_steps: List[Dict]) -> List[StepResult]:
        return [StepResult(action=s.get("action", ""),
                           target=s.get("target", ""),
                           value=s.get("value", ""),
                           ok=bool(s.get("ok", False)),
                           elapsed_ms=int(s.get("elapsed_ms", 0)),
                           note=s.get("note", "")) for s in spec_steps]

    @staticmethod
    def _task_evidence(task: Dict, result: TaskResult) -> Evidence:
        return Evidence(
            kind="task_log", source=f"task:{task['task_id']}",
            summary=f"[{result.category}] {task.get('name', '')} — "
                    f"{'success' if result.success else 'failed: ' + result.failure_reason}",
            payload={"task_id": task["task_id"],
                     "category": result.category,
                     "success": result.success,
                     "step_rate": round(result.success_rate, 3),
                     "duration_ms": result.duration_ms,
                     "failure_reason": result.failure_reason,
                     "steps": [s.__dict__ for s in result.steps]})
