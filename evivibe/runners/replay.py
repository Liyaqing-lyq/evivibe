"""ReplayRunner: deterministic evaluation from a recorded runtime trace.

The trace file (``runtime_trace.json``) is produced either by the live
Playwright harness or by the submission pipeline when the work was first
executed in the isolated environment.  Replaying it keeps every later
evaluation byte-for-byte reproducible -- the same property that lets the
benchmark ship recorded evidence instead of a fleet of live services.

Trace format (see ``data/works/demo-todo/runtime_trace.json``)::

    {
      "boot":    {"ok": true, "log": "..."},
      "tasks":   [{"task_id": ..., "name": ..., "category": ...,
                    "success": true, "failure_reason": "",
                    "steps": [{"action": "goto", "target": "/", "ok": true, ...}]}],
      "screenshots": [{"label": "home-desktop", "path": "shots/home.png"}],
      "logs":    [{"source": "app", "message": "..."}]
    }
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..schema import Evidence, TaskResult
from .base import BaseRunner, validate_tasks


class ReplayRunner(BaseRunner):
    name = "replay"

    def __init__(self, trace: Dict):
        self.trace = trace

    def run(self, work, tasks: List[Dict]) -> Tuple[List[TaskResult], List[Evidence]]:
        validate_tasks(tasks)
        evidence: List[Evidence] = []
        results: List[TaskResult] = []

        # ---- boot evidence -------------------------------------------------
        boot = self.trace.get("boot", {})
        evidence.append(Evidence(
            kind="build_log", source="replay:boot",
            summary="boot " + ("ok" if boot.get("ok") else "FAILED"),
            payload={"boot_ok": bool(boot.get("ok")),
                     "log": boot.get("log", "")}))

        # ---- task results ------------------------------------------------------
        trace_tasks = {t["task_id"]: t for t in self.trace.get("tasks", [])}
        for spec in tasks:
            rec = trace_tasks.get(spec["task_id"])
            if rec is None:
                results.append(TaskResult(
                    task_id=spec["task_id"], name=spec.get("name", ""),
                    category=spec.get("category", "core"),
                    success=False,
                    failure_reason="no recorded trace for this task"))
                continue
            tr = TaskResult(
                task_id=spec["task_id"],
                name=spec.get("name", rec.get("name", "")),
                category=spec.get("category", rec.get("category", "core")),
                steps=self._step_results(rec.get("steps", [])),
                success=bool(rec.get("success", False)),
                duration_ms=int(rec.get("duration_ms", 0)),
                failure_reason=rec.get("failure_reason", ""))
            results.append(tr)
            ev = self._task_evidence(spec, tr)
            tr.evidence_ids.append(ev.id)
            evidence.append(ev)

        # ---- auxiliary evidence -------------------------------------------------
        for shot in self.trace.get("screenshots", []):
            evidence.append(Evidence(
                kind="screenshot", source="replay:screenshot",
                summary=f"screenshot {shot.get('label', '')} "
                        f"@{shot.get('viewport', 'default')}",
                payload=shot))
        for lg in self.trace.get("logs", []):
            evidence.append(Evidence(
                kind="runtime_log", source=lg.get("source", "app"),
                summary=str(lg.get("message", ""))[:120],
                payload=lg))
        for dom in self.trace.get("dom", []):
            evidence.append(Evidence(
                kind="dom", source="replay:dom",
                summary=dom.get("summary", "DOM snapshot"),
                payload=dom))
        return results, evidence
