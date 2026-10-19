"""Evidence-bound aggregation of reviewer findings into dimension scores.

This module implements the core of the evaluation method:

1. **Evidence binding** -- every finding's ``evidence_ids`` are resolved against
   the evidence pool collected by deterministic probes.  Unbound findings from
   LLM reviewers are hallucination-prone: in ``soft`` mode their confidence is
   scaled down by ``unbound_confidence_factor``; in ``strict`` mode they are
   discarded outright.

2. **Severity-penalty scoring** -- each dimension starts at 100; every bound
   finding subtracts ``severity_penalty[severity] * confidence`` (clamped at 0)
   so that confident, evidence-backed findings dominate the score.

3. **Confidence-weighted aggregation** -- dimension confidence reflects both
   reviewer-stated confidence and evidence coverage; the final weighted total
   is ``Q = sum_d w_d * score_d`` (weights normalized to 1).

The output is fully traceable: each score point lost maps to finding ids,
each finding maps to evidence digests.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .schema import (DimensionScore, Evidence, EvaluationReport, Finding,
                     GateResult, ReviewResult, TaskResult)


def bind_evidence(
    findings: List[Finding],
    evidence: List[Evidence],
    cfg: Dict,
) -> Tuple[List[Finding], List[Finding]]:
    """Split findings into (bound, unbound) after resolving evidence ids.

    A finding is *bound* iff every id it cites exists in the evidence pool.
    Unbound findings are kept with reduced confidence (soft) or dropped
    (strict) by the caller.
    """
    ev_ids = {e.id for e in evidence}
    bound, unbound = [], []
    for f in findings:
        if f.evidence_ids and all(i in ev_ids for i in f.evidence_ids):
            bound.append(f)
        else:
            unbound.append(f)
    return bound, unbound


def apply_evidence_policy(
    reviews: List[ReviewResult],
    evidence: List[Evidence],
    cfg: Dict,
) -> List[ReviewResult]:
    """Enforce the evidence-binding policy on all review results in place."""
    mode = cfg.get("evidence_binding", "soft")
    factor = float(cfg.get("unbound_confidence_factor", 0.25))
    for r in reviews:
        bound, unbound = bind_evidence(r.findings, evidence, cfg)
        if mode == "strict":
            r.discarded_unbound = len(unbound)
            r.findings = bound
        else:
            for f in unbound:
                f.confidence *= factor
            r.discarded_unbound = 0
    return reviews


def dimension_scores(
    reviews: List[ReviewResult],
    cfg: Dict,
) -> Dict[str, DimensionScore]:
    """Compute per-dimension scores from (already policy-filtered) reviews."""
    penalty = cfg.get("severity_penalty", {})
    blend = float(cfg.get("aggregation", {}).get("prior_blend", 0.3))

    per_dim: Dict[str, List[Tuple[Finding, str]]] = {}
    priors: Dict[str, List[float]] = {}
    for r in reviews:
        for f in r.findings:
            per_dim.setdefault(f.dimension, []).append((f, r.reviewer))
        for dim, val in (r.dimension_scores or {}).items():
            if isinstance(val, (int, float)):
                priors.setdefault(dim, []).append(float(val))

    scores: Dict[str, DimensionScore] = {}
    for dim, items in per_dim.items():
        score = 100.0
        total_conf = 0.0
        for f, _reviewer in items:
            score -= penalty.get(f.severity, 5) * f.confidence
            total_conf += f.confidence
        score = max(0.0, min(100.0, score))

        # Blend with reviewer prior scores when available (e.g. LLM holistic
        # rubric scores), keeping the penalty model as the anchor.
        if dim in priors:
            prior = sum(priors[dim]) / len(priors[dim])
            prior = max(0.0, min(100.0, prior))
            score = (1 - blend) * score + blend * prior

        conf = (total_conf / len(items)) if items else 0.5
        scores[dim] = DimensionScore(dim, round(score, 2),
                                     round(conf, 3), len(items))
    return scores


def aggregate(
    work_id: str,
    reviews: List[ReviewResult],
    evidence: List[Evidence],
    task_results: List[TaskResult],
    gates: List[GateResult],
    cfg: Dict,
    reviewers: List[str] | None = None,
) -> EvaluationReport:
    """Run the full aggregation pipeline and produce the final report."""
    reviews = apply_evidence_policy(reviews, evidence, cfg)
    dim_scores = dimension_scores(reviews, cfg)

    # Dimensions with no findings keep the neutral prior; low-evidence ones
    # are flagged through a reduced confidence value.
    from . import DIMENSIONS  # local import to avoid cycles in tooling
    for dim in DIMENSIONS:
        if dim not in dim_scores:
            dim_scores[dim] = DimensionScore(dim, 85.0, 0.0, 0)

    weights = cfg.get("weights", {})
    wsum = sum(weights.get(d, 0.0) for d in DIMENSIONS)
    if wsum <= 0:
        wsum = 1.0
    weighted = sum(weights.get(d, 0.0) / wsum * dim_scores[d].score
                   for d in DIMENSIONS)

    gate_passed = all(g.passed for g in gates) if gates else True
    status = "accepted" if gate_passed else "gated"

    all_findings = [f for r in reviews for f in r.findings]
    report = EvaluationReport(
        work_id=work_id,
        gates=gates,
        dimension_scores=dim_scores,
        weighted_score=weighted if gate_passed else 0.0,
        status=status,
        findings=all_findings,
        evidence=evidence,
        task_results=task_results,
        reviewers=reviewers or [r.reviewer for r in reviews],
        config={"weights": weights,
                "evidence_binding": cfg.get("evidence_binding"),
                "reviewer_backend": cfg.get("reviewer_backend"),
                "modalities": cfg.get("modalities", {})},
    )
    return report
