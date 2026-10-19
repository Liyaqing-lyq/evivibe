"""End-to-end evaluation pipeline.

Wires together every stage for one work:

    work dir ──► analyzers (code metrics, security, process features)
                runners  (replay / playwright standard tasks)
                reviewers (mock or LLM ensemble)   ── all produce Evidence
                gates    (boot / core tasks / critical security / persistence)
                aggregator (evidence binding → dimension scores → weighted Q)

Everything the reviewers cite is collected by the deterministic stages
first, which is what makes LLM verdicts auditable.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from . import config as config_mod
from .analyzers import code_metrics, process_features, security_scan
from .aggregate import aggregate
from .gates import evaluate_gates
from .io import load_runtime_trace, load_tasks, load_work
from .report import render_markdown
from .reviewers.base import ReviewContext
from .reviewers.llm import build_llm_ensemble
from .reviewers.mock import build_mock_ensemble
from .runners.replay import ReplayRunner
from .schema import EvaluationReport, Finding


def evaluate_work(
    work_dir: str,
    tasks_path: str,
    cfg: Optional[Dict] = None,
    base_url: Optional[str] = None,
) -> EvaluationReport:
    """Run the full pipeline over one work directory."""
    cfg = cfg or config_mod.load_config()
    work = load_work(work_dir)
    tasks = load_tasks(tasks_path)

    # ---- deterministic probes ------------------------------------------------
    code_ev, code_fd = code_metrics.analyze_code(work_dir, cfg)
    sec_ev, sec_fd = security_scan.scan_security(work_dir, cfg)
    proc_ev, proc_fd = process_features.extract_process_features(work)
    analyzer_findings = code_fd + sec_fd + proc_fd

    # ---- standard user tasks ----------------------------------------------------
    runner = _make_runner(work_dir, work, cfg, base_url)
    task_results, task_ev = runner.run(work, tasks)

    evidence = code_ev + sec_ev + [proc_ev] + task_ev

    # ---- reviewer ensemble -------------------------------------------------------
    ctx = ReviewContext(work=work, evidence=evidence,
                        task_results=task_results,
                        analyzer_findings=analyzer_findings,
                        modalities=cfg.get("modalities", {}))
    if cfg.get("reviewer_backend") == "llm":
        reviewers = build_llm_ensemble(cfg)
    else:
        reviewers = build_mock_ensemble(cfg)
    reviews = [r.review(ctx) for r in reviewers]

    # ---- gates use security findings (evidence-bound only) ------------------------
    pre_findings: List[Finding] = [f for r in reviews for f in r.findings]
    gates = evaluate_gates(task_results, evidence, pre_findings, cfg)

    # ---- aggregate -------------------------------------------------------------------
    report = aggregate(
        work_id=work.work_id, reviews=reviews, evidence=evidence,
        task_results=task_results, gates=gates, cfg=cfg,
        reviewers=[r.name for r in reviewers])
    return report


def _make_runner(work_dir: str, work, cfg: Dict,
                 base_url: Optional[str]):
    if base_url:
        from .runners.playwright_runner import PlaywrightRunner
        return PlaywrightRunner(base_url)
    trace = load_runtime_trace(work_dir)
    return ReplayRunner(trace)


def evaluate_and_write(
    work_dir: str,
    tasks_path: str,
    out_dir: str,
    cfg: Optional[Dict] = None,
    base_url: Optional[str] = None,
) -> Tuple[EvaluationReport, str, str]:
    """Evaluate one work and write report.json + report.md into out_dir."""
    report = evaluate_work(work_dir, tasks_path, cfg, base_url)
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, f"{report.work_id}.json")
    md_path = os.path.join(out_dir, f"{report.work_id}.md")
    report.save(json_path)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))
    return report, json_path, md_path


def evaluate_batch(
    works_root: str,
    tasks_path: str,
    out_dir: str,
    cfg: Optional[Dict] = None,
) -> Dict:
    """Evaluate every work directory under works_root.

    Also computes agreement with expert labels when the works carry them
    (``expert_labels.overall``), producing the Spearman / Kendall / MAE
    block used in the paper's validation experiments.
    """
    from . import metrics as M
    from .report import comparison_table

    cfg = cfg or config_mod.load_config()
    results = []
    auto_scores, expert_scores, ids = [], [], []
    for name in sorted(os.listdir(works_root)):
        work_dir = os.path.join(works_root, name)
        # Skip hidden dirs and "_"-prefixed dirs (e.g. works/_template).
        if not os.path.isdir(work_dir) or name.startswith((".", "_")):
            continue
        report, _j, _m = evaluate_and_write(work_dir, tasks_path, out_dir, cfg)
        results.append(report.to_dict())
        # expert labels live in work.json -- reload them here
        from .io import load_work
        w = load_work(work_dir)
        exp = w.expert_labels.get("overall")
        if exp is not None:
            auto_scores.append(report.weighted_score
                               if report.status == "accepted" else 0.0)
            expert_scores.append(float(exp))
            ids.append(report.work_id)

    summary = {"works": results}
    if len(auto_scores) >= 2:
        summary["expert_agreement"] = M.agreement_summary(
            auto_scores, expert_scores)
    summary["comparison_table"] = comparison_table(results)

    import json as _json
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "batch_summary.json"), "w",
              encoding="utf-8") as fh:
        _json.dump(summary, fh, ensure_ascii=False, indent=2)
    return summary
