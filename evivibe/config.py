"""Evaluation configuration: weights, gate thresholds, penalties, reviewer setup.

A config is a plain JSON-serializable dict so that a full evaluation can be
reproduced by shipping (work, tasks, config) alone.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict

from . import DEFAULT_WEIGHTS, SEVERITY_PENALTY

DEFAULT_CONFIG: Dict[str, Any] = {
    "weights": dict(DEFAULT_WEIGHTS),
    "severity_penalty": dict(SEVERITY_PENALTY),

    # --- hard gates -------------------------------------------------------
    "gates": {
        "require_boot": True,
        "core_task_success_threshold": 1.0,   # all core tasks must pass
        "block_critical_security": True,
        "require_persistence": False,
    },

    # --- evidence-bound review ---------------------------------------------
    "evidence_binding": "soft",   # soft = down-weight unbound, strict = discard
    "unbound_confidence_factor": 0.25,

    # --- aggregation -------------------------------------------------------
    "aggregation": {
        # blend factor between penalty-derived score and reviewer prior score
        # (reviewer priors are only used when a reviewer emits dimension_scores)
        "prior_blend": 0.3,
        "min_dimension_confidence": 0.1,      # below -> dimension flagged low-evidence
    },

    # --- reviewers ----------------------------------------------------------
    "reviewers": ["functional", "ui", "code", "security", "process"],
    "reviewer_backend": "mock",               # mock | llm
    "llm": {
        "model": "gpt-4o-mini",
        "base_url": "",                       # OpenAI-compatible endpoint
        "api_key_env": "OPENAI_API_KEY",
        "temperature": 0.0,
        "max_tokens": 2000,
        "retries": 1,
    },

    # --- input modality toggles (for ablation, RQ2) --------------------------
    "modalities": {
        "code": True,
        "screenshot": True,
        "task_log": True,
        "prompt": True,
        "metrics": True,
        "security_scan": True,
    },
}


def load_config(path: str | None = None) -> Dict[str, Any]:
    """Deep-copied default config, optionally overlaid with a JSON file."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path:
        with open(path, "r", encoding="utf-8") as fh:
            overlay = json.load(fh)
        _deep_update(cfg, overlay)
    _validate(cfg)
    return cfg


def _deep_update(base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def _validate(cfg: Dict[str, Any]) -> None:
    weights = cfg.get("weights", {})
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    if cfg.get("evidence_binding") not in ("soft", "strict"):
        raise ValueError("evidence_binding must be 'soft' or 'strict'")
    if cfg.get("reviewer_backend") not in ("mock", "llm"):
        raise ValueError("reviewer_backend must be 'mock' or 'llm'")


def ablate(cfg: Dict[str, Any], modality: str) -> Dict[str, Any]:
    """Return a copy of cfg with one input modality disabled (ablation study)."""
    out = copy.deepcopy(cfg)
    if modality not in out["modalities"]:
        raise ValueError(f"unknown modality: {modality}")
    out["modalities"][modality] = False
    return out
