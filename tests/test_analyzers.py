import os

from evivibe.analyzers.code_metrics import analyze_code
from evivibe.analyzers.security_scan import scan_security


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_code_metrics_counts(tmp_path):
    _write(tmp_path, "app.py", "\n".join([
        "# comment line",
        "def add(a, b):",
        "    if a > 0:",
        "        return a + b",
        "    return b",
        "",
    ]))
    _write(tmp_path, "requirements.txt", "flask\n")
    _write(tmp_path, "README.md", "# demo\n")
    evidence, findings = analyze_code(str(tmp_path))
    payload = {e.summary: e for e in evidence}
    loc_ev = [e for e in evidence if "LOC" in e.summary][0]
    assert loc_ev.payload["loc"] == 4
    assert loc_ev.payload["comment_lines"] == 1
    hygiene = [e for e in evidence if "hygiene" in e.summary][0]
    assert hygiene.payload["has_dependency_manifest"] is True
    # clean small file -> no major findings
    assert all(f.severity != "major" for f in findings)


def test_code_metrics_flags_missing_manifest(tmp_path):
    _write(tmp_path, "app.py", "x = 1\n" * 200)
    evidence, findings = analyze_code(str(tmp_path))
    titles = [f.title for f in findings]
    assert any("dependency manifest" in t for t in titles)


def test_security_scan_detects_eval(tmp_path):
    _write(tmp_path, "app.py",
           "def f(expr):\n    return eval(expr)\n")
    evidence, findings = scan_security(str(tmp_path))
    assert any("eval" in f.title.lower() for f in findings)
    crit = [f for f in findings if f.severity == "critical"]
    assert crit and crit[0].evidence_ids  # bound to scan evidence


def test_security_scan_clean(tmp_path):
    _write(tmp_path, "app.py",
           "def add(a, b):\n    return a + b\n")
    evidence, findings = scan_security(str(tmp_path))
    assert findings == []
    assert any("no pattern-based" in e.summary for e in evidence)


def test_security_scan_hardcoded_secret(tmp_path):
    _write(tmp_path, "config.py",
           'API_KEY = "sk-abcdefghij1234567890"\n')
    evidence, findings = scan_security(str(tmp_path))
    assert any("credential" in f.title.lower() for f in findings)
