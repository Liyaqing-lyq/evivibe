"""Deterministic mock reviewers -- the reproducible backbone of the ensemble.

These reviewers derive findings purely from harness evidence (task outcomes,
scan hits, metric evidence, process features).  They contain **no randomness
and no LLM calls**, which gives the benchmark:

* a CI-runnable evaluation path with zero external dependencies,
* a baseline for measuring how much the LLM backend adds (RQ2 input ladder),
* ground-truth-friendly behaviour for unit tests.

The security and code reviewers adopt analyzer findings (which are already
evidence-bound), demonstrating the binding protocol end-to-end.
"""

from __future__ import annotations

from typing import Dict, List

from ..schema import Finding, ReviewResult
from .base import ReviewContext, Reviewer


class FunctionalReviewer(Reviewer):
    name = "functional"
    dimensions = ["functionality", "reliability", "ux"]

    def review(self, ctx: ReviewContext) -> ReviewResult:
        findings: List[Finding] = []
        if not ctx.allows("task_log"):
            return self._result([], "task-log modality disabled (ablation)")

        core = [t for t in ctx.task_results if t.category == "core"]
        ext = [t for t in ctx.task_results if t.category == "extension"]
        rob = [t for t in ctx.task_results
               if t.category in ("robustness", "hidden")]

        for t in core:
            if not t.success:
                findings.append(Finding(
                    dimension="functionality",
                    severity="critical" if t.success_rate < 0.5 else "major",
                    title=f"Core task failed: {t.task_id} ({t.name})",
                    detail=t.failure_reason or "task did not complete",
                    evidence_ids=t.evidence_ids,
                    confidence=0.95, reviewer=self.name))
            elif t.success_rate < 1.0:
                findings.append(Finding(
                    dimension="functionality", severity="minor",
                    title=f"Core task partially completed: {t.task_id}",
                    detail=f"step success rate {t.success_rate:.0%}",
                    evidence_ids=t.evidence_ids,
                    confidence=0.7, reviewer=self.name))

        for t in ext:
            if not t.success:
                findings.append(Finding(
                    dimension="functionality", severity="minor",
                    title=f"Extension task failed: {t.task_id} ({t.name})",
                    detail=t.failure_reason or "extension scenario broken",
                    evidence_ids=t.evidence_ids,
                    confidence=0.7, reviewer=self.name))

        rob_fail = [t for t in rob if not t.success]
        if rob:
            rate = 1 - len(rob_fail) / len(rob)
            sev = "info" if rate >= 0.8 else ("minor" if rate >= 0.5 else "major")
            if rob_fail:
                findings.append(Finding(
                    dimension="reliability", severity=sev,
                    title=f"Robustness tasks failed ({len(rob_fail)}/{len(rob)})",
                    detail="Abnormal-input scenarios (empty data, duplicate "
                           "submits, illegal characters) not handled: "
                           + "; ".join(f"{t.task_id} ({t.failure_reason})"
                                       for t in rob_fail[:3]),
                    evidence_ids=[e for t in rob_fail
                                  for e in t.evidence_ids][:5],
                    confidence=0.75, reviewer=self.name))

        # UX proxy from task duration
        slow = [t for t in ctx.task_results
                if t.success and t.duration_ms > 30000]
        for t in slow:
            findings.append(Finding(
                dimension="ux", severity="minor",
                title=f"Task unusually slow: {t.task_id} "
                      f"({t.duration_ms / 1000:.0f}s)",
                evidence_ids=t.evidence_ids,
                confidence=0.5, reviewer=self.name))

        return self._result(findings, "derived from standard-task outcomes")


class UIReviewer(Reviewer):
    name = "ui"
    dimensions = ["visual", "ux"]

    def review(self, ctx: ReviewContext) -> ReviewResult:
        findings: List[Finding] = []
        if not ctx.allows("screenshot"):
            return self._result([], "screenshot modality disabled (ablation)")

        shots = ctx.evidence_of("screenshot")
        doms = ctx.evidence_of("dom")
        viewports = {s.payload.get("viewport") for s in shots}

        if not shots:
            findings.append(Finding(
                dimension="visual", severity="major",
                title="No screenshots captured for the work",
                detail="Visual and responsive quality cannot be assessed.",
                confidence=0.6, reviewer=self.name))
        else:
            if "mobile" not in viewports and "375x812" not in viewports:
                findings.append(Finding(
                    dimension="visual", severity="minor",
                    title="No mobile-viewport screenshot captured",
                    detail="Responsive behaviour on small screens unverified.",
                    evidence_ids=[s.id for s in shots[:2]],
                    confidence=0.55, reviewer=self.name))

        for d in doms:
            if d.payload.get("overflow") or d.payload.get("horizontal_scroll"):
                findings.append(Finding(
                    dimension="visual", severity="minor",
                    title=f"Layout overflow detected: {d.summary}",
                    evidence_ids=[d.id], confidence=0.6, reviewer=self.name))
            if d.payload.get("missing_alt") or d.payload.get("empty_links"):
                findings.append(Finding(
                    dimension="visual", severity="minor",
                    title=f"Accessibility issue: {d.summary}",
                    evidence_ids=[d.id], confidence=0.5, reviewer=self.name))

        return self._result(findings, "derived from screenshot/DOM evidence")


class CodeReviewer(Reviewer):
    name = "code"
    dimensions = ["maintainability"]

    def review(self, ctx: ReviewContext) -> ReviewResult:
        if not ctx.allows("metrics") or not ctx.allows("code"):
            return self._result([], "code/metrics modality disabled (ablation)")
        adopted = [f for f in ctx.analyzer_findings
                   if f.reviewer == "code_metrics"]
        return self._result(
            [Finding(dimension=f.dimension, severity=f.severity,
                     title=f.title, detail=f.detail,
                     evidence_ids=f.evidence_ids, confidence=f.confidence,
                     reviewer=self.name) for f in adopted],
            "adopted deterministic code-metric findings")


class SecurityReviewer(Reviewer):
    name = "security"
    dimensions = ["security"]

    def review(self, ctx: ReviewContext) -> ReviewResult:
        if not ctx.allows("security_scan"):
            return self._result([], "security-scan modality disabled (ablation)")
        adopted = [f for f in ctx.analyzer_findings
                   if f.reviewer == "security_scan"]
        return self._result(
            [Finding(dimension=f.dimension, severity=f.severity,
                     title=f.title, detail=f.detail,
                     evidence_ids=f.evidence_ids, confidence=f.confidence,
                     reviewer=self.name) for f in adopted],
            "adopted deterministic security-scan findings")


class ProcessReviewer(Reviewer):
    name = "process"
    dimensions = ["collaboration"]

    def review(self, ctx: ReviewContext) -> ReviewResult:
        if not ctx.allows("prompt"):
            return self._result([], "prompt modality disabled (ablation)")
        adopted = [f for f in ctx.analyzer_findings
                   if f.reviewer == "process_features"]
        return self._result(
            [Finding(dimension=f.dimension, severity=f.severity,
                     title=f.title, detail=f.detail,
                     evidence_ids=f.evidence_ids, confidence=f.confidence,
                     reviewer=self.name) for f in adopted],
            "adopted process-feature findings")


MOCK_REVIEWERS = {
    "functional": FunctionalReviewer,
    "ui": UIReviewer,
    "code": CodeReviewer,
    "security": SecurityReviewer,
    "process": ProcessReviewer,
}


def build_mock_ensemble(cfg: Dict) -> List[Reviewer]:
    names = cfg.get("reviewers", list(MOCK_REVIEWERS))
    return [MOCK_REVIEWERS[n]() for n in names if n in MOCK_REVIEWERS]
