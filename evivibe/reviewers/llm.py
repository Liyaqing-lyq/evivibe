"""LLM-backed reviewers with evidence binding and structured output.

Design decisions that target the "LLM scoring lacks stable evidence
constraints" problem from the research plan:

1. **Evidence-first prompting** -- the model never sees free-form claims;
   it receives a numbered evidence pool (id, kind, summary, payload digest)
   and must cite ids for every finding.
2. **JSON-schema-constrained output** -- the response is parsed into
   Finding objects; malformed output triggers a single repair retry.
3. **Post-hoc binding enforcement** -- cited ids are resolved against the
   actual pool by the aggregator (see ``aggregate.apply_evidence_policy``);
   hallucinated ids mark the finding unbound and it is down-weighted or
   discarded.

The client speaks the OpenAI chat-completions protocol against any
compatible endpoint (``EVIVIBE_LLM_BASE_URL`` + ``EVIVIBE_LLM_MODEL``,
or config ``llm`` section).  No SDK dependency: plain ``urllib``.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

from ..schema import Finding, ReviewResult
from .base import ReviewContext, Reviewer

ROLE_SPECS: Dict[str, Dict[str, Any]] = {
    "functional": {
        "dimensions": ["functionality", "reliability"],
        "focus": ("Judge whether the work completes its requirement through "
                  "the standard user tasks.  Look at task logs, step "
                  "outcomes, failure reasons and durations."),
    },
    "ui": {
        "dimensions": ["visual", "ux"],
        "focus": ("Judge visual layout, consistency, responsiveness and "
                  "accessibility from screenshots, DOM evidence and task "
                  "friction (steps, durations)."),
    },
    "code": {
        "dimensions": ["maintainability"],
        "focus": ("Judge modularity, complexity, duplication, documentation "
                  "and rebuild-ability from code metrics evidence."),
    },
    "security": {
        "dimensions": ["security"],
        "focus": ("Judge risk from static-scan evidence: vulnerability "
                  "class, severity, exploitability, fix suggestion."),
    },
    "process": {
        "dimensions": ["collaboration", "innovation"],
        "focus": ("Judge the human-AI collaboration from prompt trajectory "
                  "features: clarification, error reporting, verification, "
                  "hand edits; and assess requirement novelty."),
    },
}

_SYSTEM_TEMPLATE = """You are the {name} reviewer inside EviVibe, an
evidence-bound evaluation framework for software works co-created by humans
and generative AI ("vibe coding" artifacts).

Your focus: {focus}

Rules:
1. Every finding MUST cite one or more evidence ids from the pool below.
   Findings without valid evidence citations will be discarded.
2. Severity must be one of: info, minor, major, critical.
3. Be specific and conservative: only claim what the evidence supports.
4. Respond with ONLY a JSON object, no prose, in this exact shape:
{{
  "findings": [
    {{"dimension": "<one of your dimensions>",
      "severity": "<info|minor|major|critical>",
      "title": "<short defect title>",
      "detail": "<1-3 sentence explanation>",
      "evidence_ids": ["<id from pool>"],
      "confidence": 0.0}}
  ],
  "dimension_scores": {{"<dimension>": <0-100>}},
  "rationale": "<one paragraph overall judgement>"
}}
If the evidence shows no problems, return an empty findings list.
"""


class LLMClient:
    """Minimal OpenAI-compatible chat client (stdlib only)."""

    def __init__(self, base_url: str, api_key: str, model: str,
                 temperature: float = 0.0, max_tokens: int = 2000):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str, retries: int = 1) -> str:
        body = json.dumps({
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")
        last_err: Optional[Exception] = None
        for _attempt in range(retries + 1):
            try:
                req = urllib.request.Request(
                    self.url, data=body,
                    headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {self.api_key}"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
            except Exception as exc:  # noqa: BLE001 - surface after retries
                last_err = exc
        raise RuntimeError(f"LLM call failed: {last_err}")


class LLMReviewer(Reviewer):
    """One specialized LLM judge bound to a role spec."""

    def __init__(self, role: str, client: LLMClient, retries: int = 1):
        if role not in ROLE_SPECS:
            raise ValueError(f"unknown reviewer role: {role}")
        self.role = role
        self.name = role
        self.dimensions = ROLE_SPECS[role]["dimensions"]
        self.client = client
        self.retries = retries

    def review(self, ctx: ReviewContext) -> ReviewResult:
        system = _SYSTEM_TEMPLATE.format(
            name=self.role, focus=ROLE_SPECS[self.role]["focus"])
        user = self._build_user_prompt(ctx)
        raw = self.client.complete(system, user, retries=self.retries)
        parsed = _parse_json(raw)
        if parsed is None:
            # one repair round-trip
            repair = ("Your previous output was not valid JSON. Reply with "
                      "ONLY the JSON object, no extra text.\n\n"
                      f"Previous output:\n{raw[:1500]}")
            raw = self.client.complete(system, repair, retries=0)
            parsed = _parse_json(raw)
            if parsed is None:
                return ReviewResult(
                    reviewer=self.name,
                    rationale=f"unparseable LLM output: {raw[:200]}")
        return self._to_result(parsed)

    # ------------------------------------------------------------------ #

    def _build_user_prompt(self, ctx: ReviewContext) -> str:
        parts: List[str] = []
        parts.append(f"WORK: {ctx.work.work_id} — {ctx.work.title}")
        parts.append(f"REQUIREMENT: {ctx.work.requirement[:800]}")
        parts.append("")
        parts.append("EVIDENCE POOL (cite these ids):")
        for e in ctx.evidence:
            if not self._modality_on(ctx, e.kind):
                continue
            payload = json.dumps(e.payload, ensure_ascii=False, default=str)
            parts.append(f"- id={e.id} kind={e.kind} source={e.source} :: "
                         f"{e.summary} :: payload={payload[:400]}")
        parts.append("")
        parts.append(f"Your allowed dimensions: {self.dimensions}")
        return "\n".join(parts)

    @staticmethod
    def _modality_on(ctx: ReviewContext, kind: str) -> bool:
        mapping = {
            "screenshot": "screenshot", "dom": "screenshot",
            "task_log": "task_log", "task_step": "task_log",
            "prompt_trace": "prompt", "version_history": "prompt",
            "static_scan": "security_scan", "metric": "metrics",
            "build_log": "task_log", "runtime_log": "task_log",
            "human_label": "metrics",
        }
        mod = mapping.get(kind)
        return ctx.allows(mod) if mod else True

    def _to_result(self, parsed: Dict[str, Any]) -> ReviewResult:
        findings: List[Finding] = []
        for f in parsed.get("findings", []):
            try:
                findings.append(Finding(
                    dimension=f.get("dimension", self.dimensions[0]),
                    severity=f.get("severity", "minor"),
                    title=str(f.get("title", "untitled"))[:120],
                    detail=str(f.get("detail", ""))[:1000],
                    evidence_ids=list(f.get("evidence_ids", [])),
                    confidence=float(f.get("confidence", 0.5)),
                    reviewer=self.name))
            except (ValueError, TypeError):
                continue
        scores = {}
        for k, v in (parsed.get("dimension_scores") or {}).items():
            if k in self.dimensions:
                try:
                    scores[k] = max(0.0, min(100.0, float(v)))
                except (TypeError, ValueError):
                    pass
        return ReviewResult(reviewer=self.name, findings=findings,
                            dimension_scores=scores,
                            rationale=str(parsed.get("rationale", ""))[:2000])


def build_llm_ensemble(cfg: Dict) -> List[LLMReviewer]:
    llm_cfg = cfg.get("llm", {})
    base_url = (os.environ.get("EVIVIBE_LLM_BASE_URL")
                or llm_cfg.get("base_url")
                or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    api_key = os.environ.get(
        llm_cfg.get("api_key_env", "OPENAI_API_KEY"), "")
    model = os.environ.get("EVIVIBE_LLM_MODEL") or llm_cfg.get(
        "model", "gpt-4o-mini")
    if not api_key:
        raise RuntimeError(
            "no LLM API key found; set OPENAI_API_KEY (or the env var named "
            "in config llm.api_key_env), or use --reviewer mock")
    client = LLMClient(base_url, api_key, model,
                       temperature=float(llm_cfg.get("temperature", 0.0)),
                       max_tokens=int(llm_cfg.get("max_tokens", 2000)))
    names = cfg.get("reviewers", list(ROLE_SPECS))
    return [LLMReviewer(n, client, retries=int(llm_cfg.get("retries", 1)))
            for n in names if n in ROLE_SPECS]


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON object, tolerating code fences / leading prose."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(0))
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
    return None
