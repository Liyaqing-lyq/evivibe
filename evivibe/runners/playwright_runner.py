"""PlaywrightRunner: live standard-task execution in a real browser.

Optional component -- requires ``pip install playwright`` plus
``playwright install chromium``.  Used when a work exposes a running web app
(``base_url`` in its work.json or the ``--base-url`` CLI flag).

Steps supported in a task spec::

    {"action": "goto",    "target": "/"}
    {"action": "click",   "target": "button#add"}
    {"action": "fill",    "target": "#title", "value": "Buy milk"}
    {"action": "expect",  "value": "Buy milk"}        # text visible
    {"action": "expect_absent", "value": "Buy milk"}  # text gone
    {"action": "reload"}
    {"action": "screenshot", "value": "after-add"}

Each step's outcome, timings and screenshots are recorded as Evidence, and
the step log feeds the functional reviewer and the persistence gate.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from ..schema import Evidence, StepResult, TaskResult
from .base import BaseRunner, validate_tasks


class PlaywrightRunner(BaseRunner):
    name = "playwright"

    def __init__(self, base_url: str, viewport: Dict | None = None,
                 shot_dir: str = "shots"):
        self.base_url = base_url.rstrip("/")
        self.viewport = viewport or {"width": 1280, "height": 800}
        self.shot_dir = shot_dir

    def run(self, work, tasks: List[Dict]) -> Tuple[List[TaskResult], List[Evidence]]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "playwright is not installed; use the replay runner or "
                "`pip install playwright && playwright install chromium`"
            ) from exc

        validate_tasks(tasks)
        evidence: List[Evidence] = []
        results: List[TaskResult] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport=self.viewport)
            boot_ok = True
            try:
                page.goto(self.base_url, timeout=15000)
                boot_ev = Evidence(
                    kind="build_log", source="playwright:boot",
                    summary=f"app reachable at {self.base_url}",
                    payload={"boot_ok": True, "url": self.base_url,
                             "title": page.title()})
            except Exception as exc:  # noqa: BLE001 - record & continue
                boot_ok = False
                boot_ev = Evidence(
                    kind="build_log", source="playwright:boot",
                    summary=f"app NOT reachable at {self.base_url}: {exc}",
                    payload={"boot_ok": False, "url": self.base_url,
                             "error": str(exc)})
            evidence.append(boot_ev)

            for spec in tasks:
                results.append(self._run_task(page, spec, evidence))

            browser.close()
        return results, evidence

    # ------------------------------------------------------------------ #

    def _run_task(self, page, spec: Dict, evidence: List[Evidence]) -> TaskResult:
        import os
        os.makedirs(self.shot_dir, exist_ok=True)
        tr = TaskResult(task_id=spec["task_id"], name=spec.get("name", ""),
                        category=spec.get("category", "core"))
        t0 = time.monotonic()
        for s in spec.get("steps", []):
            step = StepResult(action=s.get("action", ""),
                              target=s.get("target", ""),
                              value=s.get("value", ""))
            start = time.monotonic()
            try:
                self._exec_step(page, step, tr)
                step.ok = True
            except Exception as exc:  # noqa: BLE001 - failure IS the signal
                step.ok = False
                step.note = str(exc)[:200]
            step.elapsed_ms = int((time.monotonic() - start) * 1000)
            tr.steps.append(step)
        tr.duration_ms = int((time.monotonic() - t0) * 1000)
        tr.success = all(s.ok for s in tr.steps)
        if not tr.success:
            failed = next(s for s in tr.steps if not s.ok)
            tr.failure_reason = (f"step `{failed.action} {failed.target}"
                                 f" {failed.value}`".strip() +
                                 f" failed: {failed.note}")
        ev = self._task_evidence(spec, tr)
        tr.evidence_ids.append(ev.id)
        evidence.append(ev)
        return tr

    def _exec_step(self, page, step: StepResult, tr: TaskResult) -> None:
        act = step.action
        if act == "goto":
            page.goto(self.base_url + step.target, timeout=15000)
        elif act == "click":
            page.click(step.target, timeout=8000)
        elif act == "fill":
            page.fill(step.target, step.value, timeout=8000)
        elif act == "expect":
            page.wait_for_selector(f"text={step.value}", timeout=8000)
        elif act == "expect_absent":
            if page.locator(f"text={step.value}").count() > 0:
                raise AssertionError(f"text unexpectedly present: {step.value}")
        elif act == "reload":
            page.reload(timeout=15000)
        elif act == "screenshot":
            path = f"{self.shot_dir}/{tr.task_id}-{step.value}.png"
            page.screenshot(path=path)
            step.note = path
        else:
            raise ValueError(f"unknown action: {act}")
