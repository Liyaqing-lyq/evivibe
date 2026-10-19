"""EviVibe: an evidence-bound evaluation framework for Vibe Coding artifacts.

EviVibe evaluates complete software works co-created by humans and generative
AI ("vibe coding" artifacts) along eight quality dimensions, using a two-stage
protocol:

1. Hard gates  -- boot success, core-task success, critical security findings.
2. Soft scoring -- confidence-weighted, evidence-bound aggregation of findings
   from multiple specialized reviewers.

Every finding is expected to cite evidence collected by deterministic probes
(task runs, static analysis, scans, prompt traces).  Findings without a valid
evidence binding are down-weighted or discarded ("evidence-bound review"),
which grounds LLM judges in machine-verifiable facts.
"""

__version__ = "0.1.0"

DIMENSIONS = [
    "functionality",      # 功能正确性
    "ux",                 # 用户体验
    "visual",             # 视觉与交互
    "reliability",        # 可靠性
    "security",           # 安全性
    "maintainability",    # 可维护性
    "innovation",         # 创新性
    "collaboration",      # 人机协作
]

DIMENSION_LABELS = {
    "functionality": "Functionality",
    "ux": "User Experience",
    "visual": "Visual & Interaction",
    "reliability": "Reliability",
    "security": "Security",
    "maintainability": "Maintainability",
    "innovation": "Innovation",
    "collaboration": "Human-AI Collaboration",
}

SEVERITIES = ["info", "minor", "major", "critical"]

DEFAULT_WEIGHTS = {
    "functionality": 0.25,
    "ux": 0.12,
    "visual": 0.08,
    "reliability": 0.15,
    "security": 0.15,
    "maintainability": 0.10,
    "innovation": 0.08,
    "collaboration": 0.07,
}

# Score penalty per confirmed finding severity (applied to the dimension score).
SEVERITY_PENALTY = {"info": 2, "minor": 8, "major": 25, "critical": 60}

__all__ = [
    "DIMENSIONS",
    "DIMENSION_LABELS",
    "SEVERITIES",
    "DEFAULT_WEIGHTS",
    "SEVERITY_PENALTY",
    "__version__",
]
