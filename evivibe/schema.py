"""Core data model for EviVibe.

All evaluation artifacts (evidence, findings, task results, reviewer outputs,
gates and the final report) are plain dataclasses that serialize to / from
JSON so that every stage of an evaluation is inspectable and reproducible.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from . import DIMENSIONS, SEVERITIES

EVIDENCE_KINDS = [
    "task_log",        # standard user-task execution log
    "task_step",       # single step outcome
    "screenshot",      # captured screenshot (path)
    "dom",             # DOM snapshot / element state
    "metric",          # quantitative metric (static analysis, timing, ...)
    "static_scan",     # scanner output (security, lint, ...)
    "prompt_trace",    # prompt / dialogue record
    "version_history", # version / commit record
    "build_log",       # build or boot log
    "runtime_log",     # application runtime log
    "human_label",     # expert / user label (ground truth)
]


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _digest(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass
class Evidence:
    """A machine-collected, verifiable piece of evaluation evidence."""

    kind: str                      # one of EVIDENCE_KINDS
    source: str                    # probe / module that produced it
    summary: str                   # one-line human-readable summary
    payload: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: _uid("ev"))
    digest: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.digest:
            self.digest = _digest({"kind": self.kind, "summary": self.summary,
                                   "payload": self.payload})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Evidence":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Finding:
    """A reviewer claim about a defect or quality issue.

    ``evidence_ids`` must reference Evidence objects collected by the harness.
    A finding whose evidence ids cannot be resolved is treated as *unbound*:
    under evidence-bound review it is down-weighted (soft mode) or discarded
    (strict mode).
    """

    dimension: str                # one of DIMENSIONS
    severity: str                 # info | minor | major | critical
    title: str
    detail: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    confidence: float = 0.5       # reviewer-stated confidence in [0, 1]
    reviewer: str = "unknown"
    id: str = field(default_factory=lambda: _uid("fd"))

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            raise ValueError(f"unknown dimension: {self.dimension!r}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity: {self.severity!r}")
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Finding":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class StepResult:
    """Outcome of a single scripted interaction step."""

    action: str                   # goto | click | fill | expect | reload | ...
    target: str = ""
    value: str = ""
    ok: bool = True
    elapsed_ms: int = 0
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskResult:
    """Outcome of one standard user task executed against a work."""

    task_id: str
    name: str = ""
    category: str = "core"        # core | extension | robustness | hidden
    steps: List[StepResult] = field(default_factory=list)
    success: bool = False
    duration_ms: int = 0
    evidence_ids: List[str] = field(default_factory=list)
    failure_reason: str = ""

    @property
    def success_rate(self) -> float:
        if not self.steps:
            return 0.0
        return sum(1 for s in self.steps if s.ok) / len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        return d


@dataclass
class ReviewResult:
    """Output of one reviewer over one work."""

    reviewer: str
    findings: List[Finding] = field(default_factory=list)
    dimension_scores: Dict[str, float] = field(default_factory=dict)  # optional prior
    rationale: str = ""
    discarded_unbound: int = 0     # findings dropped by evidence binding

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "findings": [f.to_dict() for f in self.findings],
            "dimension_scores": self.dimension_scores,
            "rationale": self.rationale,
            "discarded_unbound": self.discarded_unbound,
        }


@dataclass
class GateResult:
    """Result of the hard-gate stage."""

    name: str
    passed: bool
    reason: str = ""
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DimensionScore:
    dimension: str
    score: float                  # 0..100
    confidence: float             # 0..1
    finding_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationReport:
    """The final, serializable evaluation result for one work."""

    work_id: str
    gates: List[GateResult] = field(default_factory=list)
    dimension_scores: Dict[str, DimensionScore] = field(default_factory=dict)
    weighted_score: float = 0.0
    status: str = "pending"       # accepted | gated
    findings: List[Finding] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    task_results: List[TaskResult] = field(default_factory=list)
    reviewers: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    @property
    def gate_passed(self) -> bool:
        return all(g.passed for g in self.gates)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "work_id": self.work_id,
            "status": self.status,
            "gate_passed": self.gate_passed,
            "gates": [g.to_dict() for g in self.gates],
            "weighted_score": round(self.weighted_score, 4),
            "dimension_scores": {k: v.to_dict()
                                 for k, v in self.dimension_scores.items()},
            "findings": [f.to_dict() for f in self.findings],
            "evidence": [e.to_dict() for e in self.evidence],
            "task_results": [t.to_dict() for t in self.task_results],
            "reviewers": self.reviewers,
            "config": self.config,
            "created_at": self.created_at,
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvaluationReport":
        rep = cls(work_id=d["work_id"])
        rep.gates = [GateResult(**g) for g in d.get("gates", [])]
        rep.dimension_scores = {
            k: DimensionScore(**v) for k, v in d.get("dimension_scores", {}).items()}
        rep.weighted_score = d.get("weighted_score", 0.0)
        rep.status = d.get("status", "pending")
        rep.findings = [Finding.from_dict(f) for f in d.get("findings", [])]
        rep.evidence = [Evidence.from_dict(e) for e in d.get("evidence", [])]
        rep.reviewers = d.get("reviewers", [])
        rep.config = d.get("config", {})
        rep.created_at = d.get("created_at", 0.0)
        return rep


@dataclass
class Work:
    """A vibe-coding artifact under evaluation.

    Mirrors the EviVibe data schema: requirement (R), prompt trajectory (P),
    version history (T), code (C), environment (E) and recorded runtime
    evidence / labels (U).
    """

    work_id: str
    title: str = ""
    requirement: str = ""
    path: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    prompts: List[Dict[str, Any]] = field(default_factory=list)
    versions: List[Dict[str, Any]] = field(default_factory=list)
    expert_labels: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
