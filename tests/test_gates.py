from evivibe.gates import evaluate_gates
from evivibe.schema import Evidence, Finding, TaskResult


def _task(tid, ok, category="core"):
    return TaskResult(task_id=tid, category=category, success=ok,
                      steps=[], failure_reason="" if ok else "failed")


def _boot_ev(ok=True):
    return Evidence(kind="build_log", source="boot",
                    summary="boot ok" if ok else "boot failed",
                    payload={"boot_ok": ok})


def test_boot_gate():
    cfg = {"gates": {"require_boot": True}}
    ok = evaluate_gates([], [_boot_ev(True)], [], cfg)
    bad = evaluate_gates([], [_boot_ev(False)], [], cfg)
    assert all(g.passed for g in ok if g.name == "boot")
    assert not any(g.passed for g in bad if g.name == "boot")


def test_core_task_gate():
    cfg = {"gates": {"core_task_success_threshold": 1.0}}
    tasks = [_task("T1", True), _task("T2", False)]
    gates = {g.name: g for g in evaluate_gates(tasks, [_boot_ev()], [], cfg)}
    assert not gates["core_tasks"].passed
    assert "T2" in gates["core_tasks"].reason

    gates = {g.name: g for g in evaluate_gates(
        [_task("T1", True), _task("T2", True)], [_boot_ev()], [], cfg)}
    assert gates["core_tasks"].passed


def test_security_gate_requires_evidence():
    cfg = {"gates": {"block_critical_security": True}}
    ev = Evidence(kind="static_scan", source="s", summary="eval() found")
    crit_bound = Finding(dimension="security", severity="critical",
                         title="eval", evidence_ids=[ev.id])
    crit_unbound = Finding(dimension="security", severity="critical",
                           title="imagined", evidence_ids=["ghost"])
    gates = {g.name: g for g in evaluate_gates(
        [], [ev], [crit_bound, crit_unbound], cfg)}
    assert not gates["security"].passed  # bound critical finding blocks

    gates = {g.name: g for g in evaluate_gates(
        [], [ev], [crit_unbound], cfg)}
    assert gates["security"].passed  # unbound does not block


def test_persistence_gate_optional():
    cfg = {"gates": {"require_persistence": True, "require_boot": False,
                     "block_critical_security": False}}
    gates = {g.name: g for g in evaluate_gates(
        [_task("T5", False, "persistence")], [], [], cfg)}
    assert not gates["persistence"].passed

    cfg["gates"]["require_persistence"] = False
    gates = {g.name: g for g in evaluate_gates(
        [_task("T5", False, "persistence")], [], [], cfg)}
    assert "persistence" not in gates
