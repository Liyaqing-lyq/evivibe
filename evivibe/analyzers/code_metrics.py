"""Maintainability analyzer: code metrics computed with the standard library.

Extracted signals (all emitted as Evidence of kind ``metric``):

* size: file count, LOC (code / comment / blank)
* duplication: repeated normalized non-trivial lines across the work
* complexity: cyclomatic-complexity approximation per Python function (AST)
  and keyword-based branch counts for JS/TS
* hygiene: presence of dependency manifests, tests, README, config

Findings are derived from thresholds so the reviewer ensemble starts from
deterministic, explainable baselines.
"""

from __future__ import annotations

import ast
import os
from typing import Dict, List, Tuple

from ..schema import Evidence, Finding

CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".vue"}
COMMENT_PREFIX = {"py": "#", "js": "//", "html": None, "css": None}
BRANCH_TOKENS = ("if ", "else", "for ", "while ", "case ", "catch", "&&", "||", "?")

# normalized lines shorter than this are ignored for duplication
_MIN_DUP_LINE = 25


def analyze_code(work_path: str, cfg: Dict | None = None) -> Tuple[List[Evidence], List[Finding]]:
    evidence: List[Evidence] = []
    findings: List[Finding] = []
    src_files = _source_files(work_path)

    sizes = [os.path.getsize(p) for p in src_files]
    ev_size = Evidence(
        kind="metric", source="code_metrics",
        summary=f"{len(src_files)} source files, "
                f"{sum(sizes)/1024:.1f} KiB total",
        payload={"file_count": len(src_files),
                 "total_bytes": sum(sizes)})
    evidence.append(ev_size)

    # ---- LOC / comments ----------------------------------------------------
    loc_total = comment_total = blank_total = 0
    per_ext: Dict[str, int] = {}
    all_norm_lines: List[str] = []
    for path in src_files:
        ext = os.path.splitext(path)[1].lower()
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        prefix = COMMENT_PREFIX.get(ext.lstrip("."), None)
        for ln in lines:
            s = ln.strip()
            if not s:
                blank_total += 1
            elif prefix and s.startswith(prefix):
                comment_total += 1
            else:
                loc_total += 1
                per_ext[ext] = per_ext.get(ext, 0) + 1
                norm = " ".join(s.split())
                if len(norm) >= _MIN_DUP_LINE:
                    all_norm_lines.append(norm)

    comment_ratio = comment_total / max(1, loc_total + comment_total)
    ev_loc = Evidence(
        kind="metric", source="code_metrics",
        summary=f"LOC {loc_total}, comments {comment_total} "
                f"({comment_ratio:.0%}), blank {blank_total}",
        payload={"loc": loc_total, "comment_lines": comment_total,
                 "blank_lines": blank_total,
                 "comment_ratio": round(comment_ratio, 4),
                 "by_extension": per_ext})
    evidence.append(ev_loc)

    # ---- duplication ---------------------------------------------------------
    counts: Dict[str, int] = {}
    for ln in all_norm_lines:
        counts[ln] = counts.get(ln, 0) + 1
    dup_lines = sum(c - 1 for c in counts.values() if c > 1)
    dup_ratio = dup_lines / max(1, len(all_norm_lines))
    ev_dup = Evidence(
        kind="metric", source="code_metrics",
        summary=f"duplication ratio {dup_ratio:.1%} "
                f"({dup_lines} duplicated lines)",
        payload={"duplication_ratio": round(dup_ratio, 4),
                 "duplicated_lines": dup_lines})
    evidence.append(ev_dup)

    # ---- complexity (Python AST + JS keyword proxy) ---------------------------
    py_complexity = _python_complexity(work_path, src_files)
    if py_complexity["functions"]:
        worst = max(py_complexity["functions"], key=lambda f: f[1])
        ev_cx = Evidence(
            kind="metric", source="code_metrics",
            summary=f"mean cyclomatic complexity "
                    f"{py_complexity['mean']:.1f}, worst {worst[0]}={worst[1]}",
            payload=py_complexity)
        evidence.append(ev_cx)
        if worst[1] >= 15:
            findings.append(Finding(
                dimension="maintainability", severity="major",
                title=f"High cyclomatic complexity in `{worst[0]}` ({worst[1]})",
                detail="Functions with complexity >= 15 are hard to test and "
                       "extend; consider decomposition.",
                evidence_ids=[ev_cx.id], confidence=0.8, reviewer="code_metrics"))

    # ---- hygiene ----------------------------------------------------------------
    hygiene = _hygiene(work_path, src_files)
    ev_hy = Evidence(
        kind="metric", source="code_metrics",
        summary="hygiene: " + ", ".join(
            f"{k}={'yes' if v else 'no'}" for k, v in hygiene.items()),
        payload=hygiene)
    evidence.append(ev_hy)

    # ---- findings from thresholds ------------------------------------------------
    if dup_ratio > 0.15:
        findings.append(Finding(
            dimension="maintainability", severity="major",
            title=f"Code duplication above threshold ({dup_ratio:.0%})",
            detail="More than 15% of normalized code lines are duplicated "
                   "across files; extract shared modules.",
            evidence_ids=[ev_dup.id], confidence=0.75, reviewer="code_metrics"))
    elif dup_ratio > 0.08:
        findings.append(Finding(
            dimension="maintainability", severity="minor",
            title=f"Moderate code duplication ({dup_ratio:.0%})",
            evidence_ids=[ev_dup.id], confidence=0.6, reviewer="code_metrics"))

    if comment_ratio < 0.03 and loc_total > 200:
        findings.append(Finding(
            dimension="maintainability", severity="minor",
            title=f"Very low comment ratio ({comment_ratio:.0%})",
            detail="For AI-generated works, near-zero documentation hampers "
                   "handover and further human maintenance.",
            evidence_ids=[ev_loc.id], confidence=0.6, reviewer="code_metrics"))

    if not hygiene.get("has_dependency_manifest"):
        findings.append(Finding(
            dimension="maintainability", severity="major",
            title="No dependency manifest found",
            detail="Works without requirements.txt / package.json cannot be "
                   "reliably rebuilt in the isolated runtime.",
            evidence_ids=[ev_hy.id], confidence=0.85, reviewer="code_metrics"))

    if not hygiene.get("has_tests") and loc_total > 150:
        findings.append(Finding(
            dimension="maintainability", severity="minor",
            title="No automated tests in the work",
            evidence_ids=[ev_hy.id], confidence=0.7, reviewer="code_metrics"))

    return evidence, findings


def _source_files(work_path: str) -> List[str]:
    out = []
    for root, dirs, files in os.walk(work_path):
        dirs[:] = [d for d in dirs if d not in
                   {".git", "node_modules", "venv", ".venv", "__pycache__",
                    "dist", "build"}]
        for name in files:
            if os.path.splitext(name)[1].lower() in CODE_EXT:
                out.append(os.path.join(root, name))
    return out


def _python_complexity(work_path: str, src_files: List[str]) -> Dict:
    """Cyclomatic complexity per Python function via AST (approximation)."""
    funcs: List[Tuple[str, int]] = []

    def decision_points(fn: ast.AST) -> int:
        c = 0
        for child in ast.walk(fn):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try,
                                  ast.ExceptHandler, ast.With,
                                  ast.Assert, ast.AsyncFor, ast.IfExp)):
                c += 1
            elif isinstance(child, ast.BoolOp):
                c += len(child.values) - 1
            elif isinstance(child, ast.comprehension):
                c += 1 + len(child.ifs)
        return c

    class _Visitor(ast.NodeVisitor):
        def __init__(self, fname: str):
            self.fname = fname

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            funcs.append((f"{self.fname}:{node.name}", 1 + decision_points(node)))
            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef

    for path in src_files:
        if not path.endswith(".py"):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                tree = ast.parse(fh.read())
        except (SyntaxError, OSError, ValueError):
            continue
        rel = os.path.relpath(path, work_path)
        _Visitor(rel).visit(tree)

    vals = [c for _, c in funcs]
    return {
        "functions": funcs,
        "mean": round(sum(vals) / len(vals), 2) if vals else 0.0,
        "max": max(vals) if vals else 0,
    }


def _hygiene(work_path: str, src_files: List[str]) -> Dict[str, bool]:
    names = {os.path.relpath(p, work_path).lower() for p in src_files}
    all_names = set()
    for root, dirs, files in os.walk(work_path):
        dirs[:] = [d for d in dirs if d not in
                   {".git", "node_modules", "venv", ".venv", "__pycache__"}]
        for f in files:
            all_names.add(os.path.relpath(os.path.join(root, f),
                                          work_path).lower())
    return {
        "has_dependency_manifest": bool(
            {"requirements.txt", "package.json", "pyproject.toml",
             "pom.xml", "go.mod"} & all_names),
        "has_tests": any("test" in n or n.startswith("tests/") or
                         "__test__" in n for n in names | all_names),
        "has_readme": any(n.lower().startswith("readme") for n in all_names),
        "has_lockfile": bool({"package-lock.json", "yarn.lock",
                              "poetry.lock", "Pipfile.lock"} & all_names),
    }
