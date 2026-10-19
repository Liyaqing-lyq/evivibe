"""End-to-end tests over the bundled demo works (mock backend, offline)."""

import json
import os

import pytest

from evivibe import config as config_mod
from evivibe.cli import main as cli_main
from evivibe.pipeline import evaluate_batch, evaluate_work

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = os.path.join(REPO, "data", "tasks")
GOOD = os.path.join(REPO, "data", "works", "demo-todo")
BAD = os.path.join(REPO, "data", "works", "demo-clipboard")


def _cfg():
    cfg = config_mod.load_config()
    cfg["reviewer_backend"] = "mock"
    return cfg


def test_good_work_accepted():
    report = evaluate_work(GOOD, TASKS, _cfg())
    assert report.status == "accepted"
    assert report.gate_passed
    assert 60 <= report.weighted_score <= 95
    # robustness task failed -> reliability finding present
    assert any(f.dimension == "reliability" for f in report.findings)
    # every finding resolves to evidence (mock reviewers are fully bound)
    ids = {e.id for e in report.evidence}
    assert all(set(f.evidence_ids) <= ids for f in report.findings if f.evidence_ids)


def test_bad_work_gated():
    report = evaluate_work(BAD, TASKS, _cfg())
    assert report.status == "gated"
    failed = {g.name for g in report.gates if not g.passed}
    assert "core_tasks" in failed
    assert "security" in failed  # eval() critical finding is evidence-bound
    assert report.weighted_score == 0.0


def test_strict_binding_still_passes_good_work():
    cfg = _cfg()
    cfg["evidence_binding"] = "strict"
    report = evaluate_work(GOOD, TASKS, cfg)
    assert report.status == "accepted"


def test_ablation_changes_signal():
    cfg = config_mod.ablate(_cfg(), "task_log")
    report = evaluate_work(GOOD, TASKS, cfg)
    # with task logs hidden, no reliability finding can be derived
    assert not any(f.reviewer == "functional" for f in report.findings)


def test_batch_agreement(tmp_path):
    works_root = os.path.join(REPO, "data", "works")
    summary = evaluate_batch(works_root, TASKS, str(tmp_path), _cfg())
    assert len(summary["works"]) == 2
    # both works carry expert labels -> agreement block present
    assert "expert_agreement" in summary
    ag = summary["expert_agreement"]
    assert ag["spearman"] == 1.0  # two works, correct ordering
    assert os.path.isfile(tmp_path / "batch_summary.json")


def test_cli_evaluate(tmp_path, capsys):
    rc = cli_main(["evaluate", "--work", GOOD, "--tasks", TASKS,
                   "--out", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "accepted"
    assert (tmp_path / "demo-todo.md").exists()
    assert (tmp_path / "demo-todo.json").exists()


def test_cli_evaluate_gated_exit_code(tmp_path):
    rc = cli_main(["evaluate", "--work", BAD, "--tasks", TASKS,
                   "--out", str(tmp_path)])
    assert rc == 2  # gated works exit non-zero


def test_cli_selftest():
    assert cli_main(["selftest"]) == 0


def test_report_markdown_contains_evidence(tmp_path):
    report = evaluate_work(GOOD, TASKS, _cfg())
    from evivibe.report import render_markdown
    md = render_markdown(report)
    assert "Hard gates" in md
    assert "demo-todo" in md
    assert "Evidence" in md
    assert "digest" in md
