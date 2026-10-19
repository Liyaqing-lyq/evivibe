import json

from evivibe.analyzers.process_features import extract_process_features
from evivibe.io import load_work, load_tasks
from evivibe.schema import Work


def test_process_features_mixed_trajectory():
    work = Work(work_id="w", prompts=[
        {"role": "user", "text": "做一个待办应用，可以增删改查"},
        {"role": "assistant", "text": "好的"},
        {"role": "user", "text": "报错了，500 错误，帮我修复"},
        {"role": "user", "text": "我测试了一下，修复好了"},
        {"role": "user", "text": "不对，搜索结果不对，应该模糊匹配"},
    ], versions=[
        {"version": 1, "human_edited": False},
        {"version": 2, "human_edited": True},
    ])
    ev, findings = extract_process_features(work)
    p = ev.payload
    assert p["n_prompts"] == 4
    assert p["clarification_ratio"] > 0
    assert p["error_mention_ratio"] > 0
    assert p["verification_ratio"] > 0
    assert p["human_edit_ratio"] == 0.5


def test_process_features_empty():
    ev, findings = extract_process_features(Work(work_id="w"))
    assert any(f.severity == "major" for f in findings)


def test_load_work_roundtrip(tmp_path):
    d = tmp_path / "demo"
    d.mkdir()
    (d / "work.json").write_text(json.dumps({
        "work_id": "demo", "title": "t", "requirement": "r",
        "expert_labels": {"overall": 80}}), encoding="utf-8")
    (d / "prompts.jsonl").write_text(
        '{"role": "user", "text": "hi"}\n', encoding="utf-8")
    (d / "versions.json").write_text(
        '{"versions": [{"version": 1, "human_edited": false}]}',
        encoding="utf-8")
    work = load_work(str(d))
    assert work.work_id == "demo"
    assert work.expert_labels["overall"] == 80
    assert len(work.prompts) == 1
    assert len(work.versions) == 1
