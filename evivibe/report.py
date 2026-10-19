"""Human-readable (Markdown) and machine-readable (JSON) report rendering.

Every conclusion in the report links back to evidence: dimension scores list
the findings that shaped them, findings cite evidence ids, and the appendix
dumps the evidence digests collected by the harness.
"""

from __future__ import annotations

from typing import Dict, List

from . import DIMENSION_LABELS
from .schema import EvaluationReport

_SEV_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3}


def render_markdown(report: EvaluationReport) -> str:
    lines: List[str] = []
    ev_index = {e.id: e for e in report.evidence}

    lines.append(f"# EviVibe Evaluation Report — `{report.work_id}`")
    lines.append("")
    lines.append(f"*Generated: {_ts(report.created_at)} · "
                 f"Reviewers: {', '.join(report.reviewers) or 'n/a'} · "
                 f"Backend: `{report.config.get('reviewer_backend', '?')}`*")
    lines.append("")

    # ---- verdict ----------------------------------------------------------
    if report.status == "gated":
        lines.append("> **Verdict: GATED (hard threshold failed)** — no "
                     "weighted score is issued. Fix the gate failures below "
                     "before soft scoring applies.")
    else:
        lines.append(f"> **Verdict: ACCEPTED — weighted score "
                     f"`{report.weighted_score:.1f} / 100`**")
    lines.append("")

    # ---- gates ------------------------------------------------------------
    lines.append("## 1. Hard gates")
    lines.append("")
    lines.append("| Gate | Result | Detail |")
    lines.append("|------|--------|--------|")
    for g in report.gates:
        res = "✅ PASS" if g.passed else "❌ FAIL"
        lines.append(f"| `{g.name}` | {res} | {g.reason or '-'} |")
    lines.append("")

    # ---- task results -------------------------------------------------------
    if report.task_results:
        lines.append("## 2. Standard user tasks")
        lines.append("")
        lines.append("| Task | Category | Success | Step rate | Failure |")
        lines.append("|------|----------|---------|-----------|---------|")
        for t in report.task_results:
            ok = "✅" if t.success else "❌"
            lines.append(f"| `{t.task_id}` {t.name} | {t.category} | {ok} "
                         f"| {t.success_rate:.0%} | {t.failure_reason or '-'} |")
        lines.append("")

    # ---- dimension scores -----------------------------------------------------
    lines.append("## 3. Dimension scores")
    lines.append("")
    lines.append("| Dimension | Score | Confidence | Findings |")
    lines.append("|-----------|-------|------------|----------|")
    for dim, ds in sorted(report.dimension_scores.items()):
        if report.status == "gated":
            shown = "—" if dim in ("functionality", "reliability") else ds.score
        else:
            shown = ds.score
        lines.append(f"| {DIMENSION_LABELS.get(dim, dim)} | {shown} "
                     f"| {ds.confidence:.2f} | {ds.finding_count} |")
    if report.status == "accepted":
        lines.append(f"| **Weighted total** | **{report.weighted_score:.1f}** | | |")
    lines.append("")
    if report.status == "gated":
        lines.append("*Scores shown for informational purposes only — the work "
                     "is rejected by a hard gate.*")
        lines.append("")

    # ---- findings -----------------------------------------------------------
    lines.append("## 4. Findings (evidence-linked)")
    lines.append("")
    findings = sorted(report.findings,
                      key=lambda f: _SEV_ORDER.get(f.severity, 9))
    if not findings:
        lines.append("No findings recorded.")
    for f in findings:
        sev = {"critical": "🔴", "major": "🟠",
               "minor": "🟡", "info": "🔵"}[f.severity]
        lines.append(f"### {sev} [{f.severity.upper()}] {f.title}")
        lines.append(f"*Dimension: {DIMENSION_LABELS.get(f.dimension, f.dimension)}"
                     f" · Reviewer: `{f.reviewer}` · Confidence: {f.confidence:.2f}*")
        if f.detail:
            lines.append("")
            lines.append(f.detail)
        if f.evidence_ids:
            lines.append("")
            lines.append("**Evidence:**")
            for eid in f.evidence_ids:
                ev = ev_index.get(eid)
                if ev:
                    lines.append(f"- `{ev.id}` ({ev.kind}) {ev.summary} "
                                 f"— digest `{ev.digest}`")
                else:
                    lines.append(f"- `{eid}` — ⚠️ unresolvable")
        lines.append("")

    # ---- appendix -------------------------------------------------------------
    lines.append("## Appendix: evidence pool")
    lines.append("")
    lines.append(f"{len(report.evidence)} evidence item(s) collected.")
    lines.append("")
    lines.append("| ID | Kind | Source | Summary | Digest |")
    lines.append("|----|------|--------|---------|--------|")
    for e in report.evidence:
        lines.append(f"| `{e.id}` | {e.kind} | {e.source} | "
                     f"{e.summary} | `{e.digest}` |")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by EviVibe — evidence-bound evaluation for "
                 "vibe-coding artifacts.*")
    return "\n".join(lines)


def _ts(epoch: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def comparison_table(results: List[Dict]) -> str:
    """Markdown summary table across works (for `evivibe batch`)."""
    lines = ["| Work | Status | Weighted score | Gated by |",
             "|------|--------|----------------|----------|"]
    for r in results:
        gated = ", ".join(g["name"] for g in r.get("gates", [])
                          if not g.get("passed")) or "-"
        lines.append(f"| `{r['work_id']}` | {r['status']} "
                     f"| {r.get('weighted_score', 0):.1f} | {gated} |")
    return "\n".join(lines)
