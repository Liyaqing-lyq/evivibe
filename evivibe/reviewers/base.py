"""Reviewer base class and the shared review context.

Five specialized reviewers mirror the research plan:

===========  ================================  ==========================
Reviewer     Inputs (modalities)               Output focus
===========  ================================  ==========================
functional   task logs, step outcomes          task success, failure steps
ui           screenshots, DOM, viewports        layout, consistency, a11y
code         source, metrics, dependency data   modularity, complexity
security     static / dependency scans          vulnerability classes
process      prompts, versions, test records    collaboration behaviour
===========  ================================  ==========================

Each reviewer returns findings that MUST cite evidence ids; the aggregator
enforces that binding.  Reviewers are interchangeable: the deterministic
``mock`` backend reproduces the ensemble offline, the ``llm`` backend calls
an OpenAI-compatible judge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from ..schema import Evidence, Finding, ReviewResult, TaskResult, Work


@dataclass
class ReviewContext:
    """Everything a reviewer is allowed to see for one work."""

    work: Work
    evidence: List[Evidence] = field(default_factory=list)
    task_results: List[TaskResult] = field(default_factory=list)
    analyzer_findings: List[Finding] = field(default_factory=list)
    modalities: Dict[str, bool] = field(default_factory=dict)

    def evidence_of(self, *kinds: str) -> List[Evidence]:
        return [e for e in self.evidence if e.kind in kinds]

    def allows(self, modality: str) -> bool:
        return self.modalities.get(modality, True)


class Reviewer:
    """Base reviewer: subclasses implement :meth:`review`."""

    name: str = "reviewer"
    dimensions: List[str] = []

    def review(self, ctx: ReviewContext) -> ReviewResult:
        raise NotImplementedError

    def _result(self, findings: List[Finding], rationale: str = "") -> ReviewResult:
        return ReviewResult(reviewer=self.name, findings=findings,
                            rationale=rationale)
