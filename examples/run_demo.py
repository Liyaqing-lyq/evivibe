"""Offline demo: evaluate both bundled works with the mock ensemble.

Run from the repository root:

    python examples/run_demo.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evivibe import config as config_mod          # noqa: E402
from evivibe.pipeline import evaluate_batch        # noqa: E402
from evivibe.report import render_markdown         # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    cfg = config_mod.load_config()
    cfg["reviewer_backend"] = "mock"

    out = os.path.join(REPO, "evivibe-output")
    summary = evaluate_batch(
        os.path.join(REPO, "data", "works"),
        os.path.join(REPO, "data", "tasks"),
        out, cfg)

    print(summary["comparison_table"])
    print()
    if "expert_agreement" in summary:
        print("Agreement with expert labels:",
              json.dumps(summary["expert_agreement"], indent=2))
    print(f"\nFull reports written under {out}/")


if __name__ == "__main__":
    main()
