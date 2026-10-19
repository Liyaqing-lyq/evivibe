import json

from evivibe.reviewers.base import ReviewContext
from evivibe.reviewers.llm import LLMClient, LLMReviewer, _parse_json
from evivibe.schema import Evidence, StepResult, TaskResult, Work


class FakeClient:
    """Records prompts; returns a canned JSON response."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, system, user, retries=1):
        self.calls.append((system, user))
        return self.response


def _ctx():
    ev = Evidence(kind="task_log", source="task:T1",
                  summary="core task failed: element not found")
    task = TaskResult(task_id="T1", category="core", success=False,
                      steps=[StepResult(action="click", ok=False)],
                      failure_reason="element not found",
                      evidence_ids=[ev.id])
    return ReviewContext(
        work=Work(work_id="w", title="t", requirement="r"),
        evidence=[ev], task_results=[task],
        analyzer_findings=[], modalities={})


def test_parse_json_tolerates_fences():
    assert _parse_json('{"a": 1}') == {"a": 1}
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json('Sure! {"a": 1} hope that helps') == {"a": 1}
    assert _parse_json("not json at all") is None


def test_llm_reviewer_evidence_first_prompt():
    client = FakeClient(json.dumps({"findings": [], "dimension_scores": {}}))
    reviewer = LLMReviewer("functional", client)
    reviewer.review(_ctx())
    _system, user = client.calls[0]
    # the evidence pool with ids must be in the prompt
    assert "EVIDENCE POOL" in user
    assert "id=ev-" in user
    # citation rule must be stated
    assert "evidence_ids" in _system


def test_llm_reviewer_parses_findings():
    ev = Evidence(kind="task_log", source="task:T1", summary="failed")
    resp = {
        "findings": [{
            "dimension": "functionality", "severity": "major",
            "title": "core task fails", "detail": "button missing",
            "evidence_ids": [ev.id], "confidence": 0.9}],
        "dimension_scores": {"functionality": 40},
        "rationale": "task evidence shows failure"}
    client = FakeClient(json.dumps(resp))
    reviewer = LLMReviewer("functional", client)
    ctx = ReviewContext(work=Work(work_id="w"), evidence=[ev],
                        task_results=[], analyzer_findings=[],
                        modalities={})
    result = reviewer.review(ctx)
    assert len(result.findings) == 1
    assert result.findings[0].evidence_ids == [ev.id]
    assert result.dimension_scores["functionality"] == 40


def test_llm_reviewer_drops_invalid_severity():
    resp = {"findings": [{"dimension": "functionality",
                          "severity": "catastrophic", "title": "x"}]}
    client = FakeClient(json.dumps(resp))
    reviewer = LLMReviewer("functional", client)
    result = reviewer.review(_ctx())
    assert result.findings == []


def test_modality_filter_hides_evidence():
    ev = Evidence(kind="static_scan", source="s", summary="eval found")
    ctx = ReviewContext(work=Work(work_id="w"), evidence=[ev],
                        task_results=[], analyzer_findings=[],
                        modalities={"security_scan": False})
    client = FakeClient(json.dumps({"findings": []}))
    reviewer = LLMReviewer("security", client)
    reviewer.review(ctx)
    _sys, user = client.calls[0]
    assert "static_scan" not in user
