"""Hard gates: pass/fail conditions evaluated before any soft scoring.

A work that fails any gate is marked ``gated`` and receives no weighted total
-- per the two-stage protocol (hard threshold -> multi-dimensional scoring ->
evidence-linked explanation), a broken work must not be averaged away by a
high soft score.
"""

from __future__ import annotations

from typing import Dict, List

from .schema import Evidence, Finding, GateResult, TaskResult


def evaluate_gates(
    task_results: List[TaskResult],
    evidence: List[Evidence],
    findings: List[Finding],
    cfg: Dict,
) -> List[GateResult]:
    """Evaluate all hard gates from harness outputs.

    Returns the list of GateResult (one per gate). ``all(g.passed)`` decides
    whether the work proceeds to soft scoring.
    """
    gates: List[GateResult] = []
    gcfg = cfg.get("gates", {})

    # ---- G1: boot / build ------------------------------------------------
    if gcfg.get("require_boot", True):
        boot_ev = [e for e in evidence if e.kind in ("build_log", "runtime_log")
                   and e.payload.get("boot_ok") is True]
        if boot_ev:
            gates.append(GateResult("boot", True,
                                    evidence_ids=[boot_ev[0].id]))
        else:
            fail_ev = [e for e in evidence if e.kind in ("build_log", "runtime_log")]
            ids = [fail_ev[0].id] if fail_ev else []
            reason = fail_ev[0].summary if fail_ev else "no boot/build evidence found"
            gates.append(GateResult("boot", False, reason, ids))

    # ---- G2: core task success --------------------------------------------
    threshold = float(gcfg.get("core_task_success_threshold", 1.0))
    core = [t for t in task_results if t.category == "core"]
    if not core:
        gates.append(GateResult(
            "core_tasks", False, "no core task results were produced"))
    else:
        rate = sum(1 for t in core if t.success) / len(core)
        ok = rate >= threshold
        failed = [t.task_id for t in core if not t.success]
        reason = "" if ok else (
            f"core task success rate {rate:.2f} < {threshold:.2f}; "
            f"failed: {', '.join(failed) or 'none'}")
        gates.append(GateResult(
            "core_tasks", ok, reason,
            [eid for t in core for eid in t.evidence_ids]))

    # ---- G3: critical security findings ------------------------------------
    if gcfg.get("block_critical_security", True):
        ev_ids = {e.id for e in evidence}
        crit = [f for f in findings
                if f.dimension == "security" and f.severity == "critical"]
        # Only critical findings whose cited evidence actually resolves
        # block the gate (evidence-bound gate).
        blocked = [f for f in crit
                   if f.evidence_ids and set(f.evidence_ids) <= ev_ids]
        ok = not blocked
        reason = "" if ok else (
            f"{len(blocked)} evidence-bound critical security finding(s): "
            + "; ".join(f.title for f in blocked[:3]))
        gates.append(GateResult("security", ok, reason,
                                [eid for f in blocked for eid in f.evidence_ids]))

    # ---- G4: data persistence (optional) -----------------------------------
    if gcfg.get("require_persistence", False):
        pers = [t for t in task_results if t.category == "persistence"]
        ok = bool(pers) and all(t.success for t in pers)
        reason = "" if ok else "data persistence check failed or missing"
        gates.append(GateResult("persistence", ok, reason,
                                [eid for t in pers for eid in t.evidence_ids]))

    return gates
