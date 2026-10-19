"""Human-AI collaboration process features (the "process layer" of EviVibe).

Extracts interpretable features from the prompt trajectory (P) and version
history (T) of a work.  These features are what the *process reviewer*
consumes and what regression analyses use to test H4 (do clarification,
error-verification and iteration behaviours predict final quality?).

Features:

* ``n_prompts``            -- number of user turns
* ``avg_prompt_chars``     -- mean prompt length
* ``clarification_ratio``  -- share of turns asking the AI to clarify/rethink
* ``error_mention_ratio``  -- share of turns reporting bugs / failed runs
* ``verification_ratio``   -- share of turns describing manual testing
* ``n_versions``           -- number of saved versions
* ``human_edit_ratio``     -- share of versions flagged as hand-edited
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ..schema import Evidence, Finding, Work

_CLARIFY = re.compile(r"(?i)(clarif|不明白|没理解|重新|不对|不是这个|应该|"
                      r"requirements?|需求是|我想要|改为|instead)")
_ERROR = re.compile(r"(?i)(error|bug|报错|失败|异常|crash|不工作|broken|"
                    r"fix|修复|fix(ed)? this|traceback)")
_VERIFY = re.compile(r"(?i)(我测试|tested|测试了|运行了|验证|check(ed)?|"
                     r"tried|试了|manually)")


def extract_process_features(work: Work) -> Tuple[Evidence, List[Finding]]:
    """Compute process features and derive collaboration findings."""
    prompts = [p for p in work.prompts if p.get("role", "user") == "user"]
    n = len(prompts)
    texts = [str(p.get("text", "")) for p in prompts]
    avg_len = sum(len(t) for t in texts) / n if n else 0.0

    def ratio(pattern: re.Pattern) -> float:
        if not texts:
            return 0.0
        return sum(1 for t in texts if pattern.search(t)) / len(texts)

    clarify_r = ratio(_CLARIFY)
    error_r = ratio(_ERROR)
    verify_r = ratio(_VERIFY)

    versions = work.versions or []
    n_versions = len(versions)
    human_edits = sum(1 for v in versions if v.get("human_edited"))
    human_edit_ratio = human_edits / n_versions if n_versions else 0.0

    features: Dict = {
        "n_prompts": n,
        "avg_prompt_chars": round(avg_len, 1),
        "clarification_ratio": round(clarify_r, 3),
        "error_mention_ratio": round(error_r, 3),
        "verification_ratio": round(verify_r, 3),
        "n_versions": n_versions,
        "human_edit_ratio": round(human_edit_ratio, 3),
    }

    ev = Evidence(
        kind="prompt_trace", source="process_features",
        summary=(f"{n} user prompts, {n_versions} versions; "
                 f"clarify {clarify_r:.0%}, error-report {error_r:.0%}, "
                 f"verify {verify_r:.0%}, hand-edit {human_edit_ratio:.0%}"),
        payload=features)

    findings = _findings(features, ev)
    return ev, findings


def _findings(f: Dict, ev: Evidence) -> List[Finding]:
    out: List[Finding] = []

    if f["n_prompts"] == 0:
        out.append(Finding(
            dimension="collaboration", severity="major",
            title="No prompt trajectory recorded",
            detail="Without the human-AI dialogue the collaboration dimension "
                   "cannot be assessed; works should submit their trajectory.",
            evidence_ids=[ev.id], confidence=0.9, reviewer="process_features"))
        return out

    if f["verification_ratio"] < 0.1 and f["n_prompts"] >= 5:
        out.append(Finding(
            dimension="collaboration", severity="minor",
            title="Little evidence of manual verification during development",
            detail=(f"Only {f['verification_ratio']:.0%} of {f['n_prompts']} "
                    "turns mention testing or verifying the running app. "
                    "Human verification is a key defence against plausible-"
                    "but-broken generations."),
            evidence_ids=[ev.id], confidence=0.6, reviewer="process_features"))

    if f["error_mention_ratio"] > 0.6:
        out.append(Finding(
            dimension="collaboration", severity="info",
            title="Iterative debugging loop present",
            detail=(f"{f['error_mention_ratio']:.0%} of turns report errors "
                    "and drive fixes -- a healthy signal of verification-"
                    "driven iteration."),
            evidence_ids=[ev.id], confidence=0.5, reviewer="process_features"))

    if f["human_edit_ratio"] == 0.0 and f["n_versions"] >= 3:
        out.append(Finding(
            dimension="collaboration", severity="info",
            title="Fully AI-mediated development",
            detail="No version is flagged as hand-edited; the work appears "
                   "to be pure prompt-driven development.",
            evidence_ids=[ev.id], confidence=0.4, reviewer="process_features"))
    return out
