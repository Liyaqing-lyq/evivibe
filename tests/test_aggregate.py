from evivibe.aggregate import (apply_evidence_policy, bind_evidence,
                                 dimension_scores)
from evivibe.schema import Evidence, Finding, ReviewResult


def _ev(summary="something happened"):
    return Evidence(kind="task_log", source="t", summary=summary)


def test_bind_evidence_resolves_ids():
    ev = _ev()
    bound = Finding(dimension="security", severity="major", title="x",
                    evidence_ids=[ev.id], confidence=0.9)
    unbound = Finding(dimension="security", severity="major", title="y",
                      evidence_ids=["ev-hallucinated"], confidence=0.9)
    b, u = bind_evidence([bound, unbound], [ev], {})
    assert [f.id for f in b] == [bound.id]
    assert [f.id for f in u] == [unbound.id]


def test_soft_mode_downweights_unbound():
    ev = _ev()
    unbound = Finding(dimension="security", severity="major", title="y",
                      evidence_ids=["nope"], confidence=1.0)
    review = ReviewResult(reviewer="security", findings=[unbound])
    cfg = {"evidence_binding": "soft", "unbound_confidence_factor": 0.25}
    apply_evidence_policy([review], [ev], cfg)
    assert abs(review.findings[0].confidence - 0.25) < 1e-9


def test_strict_mode_discards_unbound():
    ev = _ev()
    bound = Finding(dimension="security", severity="major", title="x",
                    evidence_ids=[ev.id])
    unbound = Finding(dimension="security", severity="critical", title="y",
                      evidence_ids=[])
    review = ReviewResult(reviewer="security", findings=[bound, unbound])
    cfg = {"evidence_binding": "strict"}
    apply_evidence_policy([review], [ev], cfg)
    assert len(review.findings) == 1
    assert review.discarded_unbound == 1


def test_dimension_scores_severity_penalty():
    ev = _ev()
    f1 = Finding(dimension="security", severity="critical", title="a",
                 evidence_ids=[ev.id], confidence=1.0)
    f2 = Finding(dimension="security", severity="minor", title="b",
                 evidence_ids=[ev.id], confidence=0.5)
    cfg = {"severity_penalty": {"critical": 60, "minor": 8},
           "aggregation": {"prior_blend": 0.0}}
    scores = dimension_scores(
        [ReviewResult(reviewer="sec", findings=[f1, f2])], cfg)
    # 100 - 60*1.0 - 8*0.5 = 36
    assert abs(scores["security"].score - 36.0) < 1e-6


def test_dimension_scores_clamp_and_prior():
    ev = _ev()
    f = Finding(dimension="security", severity="critical", title="a",
                evidence_ids=[ev.id], confidence=1.0)
    cfg = {"severity_penalty": {"critical": 60},
           "aggregation": {"prior_blend": 0.5}}
    review = ReviewResult(reviewer="sec", findings=[f],
                          dimension_scores={"security": 90.0})
    scores = dimension_scores([review], cfg)
    # penalty score 40, prior 90, blend 0.5 -> 65
    assert abs(scores["security"].score - 65.0) < 1e-6
