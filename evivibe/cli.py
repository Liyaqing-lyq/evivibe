"""EviVibe command-line interface.

    evivibe evaluate --work <dir> --tasks <file|dir> [--out <dir>]
                       [--reviewer mock|llm] [--config <file>]
                       [--base-url <url>] [--strict]

    evivibe batch    --works <root> --tasks <file|dir> [--out <dir>]

    evivibe ablate   --work <dir> --tasks <file|dir> --modality <name>

    evivibe selftest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import List

from . import __version__, config as config_mod
from .pipeline import evaluate_and_write, evaluate_batch, evaluate_work


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evivibe",
        description="Evidence-bound evaluation framework for vibe-coding "
                    "software artifacts.")
    parser.add_argument("--version", action="version",
                        version=f"evivibe {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ev = sub.add_parser("evaluate", help="evaluate a single work")
    p_ev.add_argument("--work", required=True, help="work directory")
    p_ev.add_argument("--tasks", required=True,
                      help="task spec JSON file or directory")
    p_ev.add_argument("--out", default="evivibe-output",
                      help="output directory (default: evivibe-output)")
    p_ev.add_argument("--reviewer", choices=["mock", "llm"], default=None)
    p_ev.add_argument("--config", default=None, help="JSON config overlay")
    p_ev.add_argument("--base-url", default=None,
                      help="live app base URL (switches to Playwright)")
    p_ev.add_argument("--strict", action="store_true",
                      help="strict evidence binding: discard unbound findings")

    p_ba = sub.add_parser("batch", help="evaluate every work under a root")
    p_ba.add_argument("--works", required=True)
    p_ba.add_argument("--tasks", required=True)
    p_ba.add_argument("--out", default="evivibe-output")
    p_ba.add_argument("--reviewer", choices=["mock", "llm"], default=None)
    p_ba.add_argument("--config", default=None)

    p_ab = sub.add_parser("ablate",
                          help="evaluate with one input modality disabled")
    p_ab.add_argument("--work", required=True)
    p_ab.add_argument("--tasks", required=True)
    p_ab.add_argument("--modality", required=True,
                      choices=["code", "screenshot", "task_log", "prompt",
                               "metrics", "security_scan"])
    p_ab.add_argument("--out", default="evivibe-output")
    p_ab.add_argument("--config", default=None)

    sub.add_parser("selftest", help="run a quick offline self-check")

    args = parser.parse_args(argv)

    if args.command == "selftest":
        return _selftest()

    if args.command == "evaluate":
        cfg = config_mod.load_config(args.config)
        if args.reviewer:
            cfg["reviewer_backend"] = args.reviewer
        if args.strict:
            cfg["evidence_binding"] = "strict"
        report, jpath, mpath = evaluate_and_write(
            args.work, args.tasks, args.out, cfg, args.base_url)
        print(json.dumps({
            "work_id": report.work_id,
            "status": report.status,
            "weighted_score": round(report.weighted_score, 2),
            "findings": len(report.findings),
            "report_json": jpath,
            "report_md": mpath,
        }, ensure_ascii=False, indent=2))
        return 0 if report.status == "accepted" else 2

    if args.command == "batch":
        cfg = config_mod.load_config(args.config)
        if args.reviewer:
            cfg["reviewer_backend"] = args.reviewer
        summary = evaluate_batch(args.works, args.tasks, args.out, cfg)
        print(summary["comparison_table"])
        if "expert_agreement" in summary:
            print()
            print("Expert agreement:",
                  json.dumps(summary["expert_agreement"]))
        print(f"\nBatch summary written to {args.out}/batch_summary.json")
        return 0

    if args.command == "ablate":
        cfg = config_mod.load_config(args.config)
        cfg = config_mod.ablate(cfg, args.modality)
        full = evaluate_work(args.work, args.tasks, cfg)
        ablated = evaluate_work(args.work, args.tasks, cfg)
        print(json.dumps({
            "modality_disabled": args.modality,
            "full_score": round(full.weighted_score, 2),
            "ablated_score": round(ablated.weighted_score, 2),
            "delta": round(full.weighted_score - ablated.weighted_score, 2),
        }, indent=2))
        return 0

    return 1


def _selftest() -> int:
    """Offline smoke test on a bundled demo work (no network, no LLM)."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(pkg_dir)
    work = os.path.join(repo, "data", "works", "demo-todo")
    tasks = os.path.join(repo, "data", "tasks")
    if not os.path.isdir(work):
        print("demo data not found; run from the repository root",
              file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        cfg = config_mod.load_config()
        cfg["reviewer_backend"] = "mock"
        report, _j, _m = evaluate_and_write(work, tasks, tmp, cfg)
        print(f"selftest OK: work={report.work_id} "
              f"status={report.status} score={report.weighted_score:.1f} "
              f"findings={len(report.findings)} "
              f"evidence={len(report.evidence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
