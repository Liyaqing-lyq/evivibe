"""Security analyzer: pattern-based static scan over the work's sources.

Covers the high-risk classes named in the benchmark's security dimension:
dynamic code execution, command injection, unsafe deserialization, hardcoded
secrets, SQL string building, debug modes, weak hashing and XSS sinks.

Every hit is emitted as Evidence (kind ``static_scan``) with the exact file /
line, plus a Finding whose evidence binding makes it gate-eligible.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple

from ..schema import Evidence, Finding

SCAN_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".vue", ".env",
            ".json", ".yml", ".yaml", ".toml", ".cfg"}

# (id, regex, severity, title, dimension, langs)
PATTERNS = [
    ("py-eval", r"\beval\s*\(", "critical", "Dynamic code execution via eval()",
     {"py"}),
    ("py-exec", r"\bexec\s*\(", "critical", "Dynamic code execution via exec()",
     {"py"}),
    ("py-pickle", r"pickle\.loads?\s*\(", "major",
     "Unsafe deserialization with pickle", {"py"}),
    ("py-shell-true", r"subprocess\.\w+\([^)]*shell\s*=\s*True", "critical",
     "Subprocess call with shell=True (command injection risk)", {"py"}),
    ("py-os-system", r"\bos\.system\s*\(", "major",
     "Shell execution via os.system", {"py"}),
    ("py-sql-concat", r"(execute|executemany)\s*\(\s*[fF]?[\"']{3}?\s*(SELECT|"
     r"INSERT|UPDATE|DELETE)[^\"']*[\"']\s*%|execute\s*\(\s*f[\"']",
     "major", "SQL statement built through string formatting", {"py"}),
    ("py-flask-debug", r"app\.run\([^)]*debug\s*=\s*True", "major",
     "Application started with debug=True", {"py"}),
    ("py-md5", r"hashlib\.(md5|sha1)\s*\(", "minor",
     "Weak hash algorithm (md5/sha1)", {"py"}),
    ("py-jwt-none", r"algorithms\s*=\s*\[[\"']none[\"']", "critical",
     "JWT verification with 'none' algorithm", {"py"}),
    ("secret-key", r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|"
     r"password)\s*[=:]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']", "critical",
     "Hardcoded credential in source", {"any"}),
    ("private-key", r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "critical",
     "Embedded private key material", {"any"}),
    ("js-eval", r"\beval\s*\(", "critical", "Dynamic code execution via eval()",
     {"js"}),
    ("js-innerhtml", r"\.innerHTML\s*=", "major",
     "Potential XSS sink (innerHTML assignment)", {"js"}),
    ("js-document-write", r"document\.write\s*\(", "major",
     "Potential XSS sink (document.write)", {"js"}),
    ("mixed-content", r"http://(?!localhost|127\.0\.0\.1)[^\s\"']+", "minor",
     "Remote resource over plain HTTP (mixed content)", {"js", "html"}),
]

_LANG_BY_EXT = {
    ".py": "py", ".js": "js", ".jsx": "js", ".ts": "js", ".tsx": "js",
    ".html": "html", ".vue": "js", ".env": "any", ".json": "any",
    ".yml": "any", ".yaml": "any", ".toml": "any", ".cfg": "any",
}

_COMPILED = [(pid, re.compile(rx), sev, title)
             for pid, rx, sev, title, _langs in PATTERNS]
_PAT_LANGS = {pid: langs for pid, _rx, _sev, _t, langs in PATTERNS}


def scan_security(work_path: str,
                  cfg: Dict | None = None) -> Tuple[List[Evidence], List[Finding]]:
    evidence: List[Evidence] = []
    findings: List[Finding] = []

    hits: List[Dict] = []
    for root, dirs, files in os.walk(work_path):
        dirs[:] = [d for d in dirs if d not in
                   {".git", "node_modules", "venv", ".venv", "__pycache__"}]
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext not in SCAN_EXT:
                continue
            lang = _LANG_BY_EXT.get(ext, "any")
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8",
                          errors="replace") as fh:
                    for lineno, line in enumerate(fh, 1):
                        stripped = line.strip()
                        if not stripped or stripped.startswith(("#", "//", "*")):
                            continue
                        for pid, rx, sev, title in _COMPILED:
                            langs = _PAT_LANGS[pid]
                            if langs != {"any"} and lang not in langs:
                                continue
                            if rx.search(line):
                                hits.append({
                                    "pattern": pid, "file":
                                        os.path.relpath(path, work_path),
                                    "line": lineno,
                                    "severity": sev,
                                    "title": title,
                                    "excerpt": stripped[:160],
                                })
            except OSError:
                continue

    # Aggregate per pattern into one evidence + one finding.
    by_pattern: Dict[str, List[Dict]] = {}
    for h in hits:
        by_pattern.setdefault(h["pattern"], []).append(h)

    for pid, group in sorted(by_pattern.items()):
        sev = group[0]["severity"]
        title = group[0]["title"]
        locations = [f"{h['file']}:{h['line']}" for h in group]
        ev = Evidence(
            kind="static_scan", source="security_scan",
            summary=f"{title} — {len(group)} occurrence(s): "
                    f"{', '.join(locations[:3])}"
                    + (" …" if len(locations) > 3 else ""),
            payload={"pattern": pid, "severity": sev,
                     "locations": locations,
                     "excerpts": [h["excerpt"] for h in group[:5]]})
        evidence.append(ev)
        findings.append(Finding(
            dimension="security", severity=sev, title=title,
            detail=f"Detected at: {', '.join(locations[:8])}"
                   + (" …" if len(locations) > 8 else ""),
            evidence_ids=[ev.id],
            confidence=0.9 if sev in ("critical", "major") else 0.7,
            reviewer="security_scan"))

    # Summary evidence even when clean (supports "no findings" verdicts).
    if not hits:
        evidence.append(Evidence(
            kind="static_scan", source="security_scan",
            summary="no pattern-based security hits",
            payload={"hits": 0}))
    return evidence, findings
