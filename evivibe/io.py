"""Work / task / trajectory loading from a benchmark directory.

A *work directory* follows the EviVibe data schema (the A = {R, P, T, C, E, U}
model from the research plan):

    works/<work-id>/
        work.json          # metadata, requirement (R), expert labels (U)
        prompts.jsonl      # one prompt / dialogue record per line (P)
        versions.json      # version / commit history (T)
        runtime_trace.json # recorded standard-task evidence (E) for replay
        <source files>     # the artifact itself (C)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .schema import Work

EXCLUDE_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__",
                "dist", "build", ".next", ".idea", "*.egg-info"}


def load_work(work_dir: str) -> Work:
    """Load a work description from its directory."""
    meta_path = os.path.join(work_dir, "work.json")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(f"work.json not found in {work_dir}")
    with open(meta_path, "r", encoding="utf-8") as fh:
        meta = json.load(fh)

    prompts = _load_jsonl(os.path.join(work_dir, "prompts.jsonl"))
    versions = _load_json(os.path.join(work_dir, "versions.json"), default=[])
    if isinstance(versions, dict):
        versions = versions.get("versions", [])

    return Work(
        work_id=meta.get("work_id") or os.path.basename(
            os.path.abspath(work_dir)),
        title=meta.get("title", ""),
        requirement=meta.get("requirement", ""),
        path=os.path.abspath(work_dir),
        meta=meta,
        prompts=prompts,
        versions=versions,
        expert_labels=meta.get("expert_labels", {}),
    )


def load_tasks(tasks_path: str) -> List[Dict[str, Any]]:
    """Load standard user tasks from a JSON file (or a directory of them)."""
    if os.path.isdir(tasks_path):
        tasks: List[Dict[str, Any]] = []
        for name in sorted(os.listdir(tasks_path)):
            if name.endswith(".json"):
                tasks.extend(_load_json(os.path.join(tasks_path, name),
                                        default=[]))
        return tasks
    return _load_json(tasks_path, default=[])


def load_runtime_trace(work_dir: str) -> Dict[str, Any]:
    """Load recorded runtime evidence for the replay runner."""
    path = os.path.join(work_dir, "runtime_trace.json")
    return _load_json(path, default={})


def iter_source_files(work_dir: str) -> List[str]:
    """Yield source file paths, excluding vendored / build directories."""
    out: List[str] = []
    for root, dirs, files in os.walk(work_dir):
        dirs[:] = [d for d in dirs
                   if d not in EXCLUDE_DIRS and not d.endswith(".egg-info")]
        for name in files:
            out.append(os.path.join(root, name))
    return out


def _load_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_json(path: str, default: Any = None) -> Any:
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
