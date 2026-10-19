"""Self-contained HTML report renderer.

Produces a single .html file with no external dependencies (pure inline
SVG + CSS), so it can be opened offline in any browser. This is the
human-facing visualisation layer of EviVibe: radar chart for the eight
quality dimensions, gate status strip, defect list bound to evidence,
and the full evidence pool.

The renderer consumes the same report JSON as ``report.py``; nothing
here re-computes scores — it is a pure presentation layer.
"""

from __future__ import annotations

import html
import json
import math
from typing import Dict, List

from .schema import EvaluationReport

_DIM_LABELS = {
    "functionality": "功能完备",
    "ux": "交互易用",
    "visual": "视觉表现",
    "reliability": "鲁棒性",
    "security": "安全",
    "maintainability": "可维护",
    "innovation": "创新性",
    "collaboration": "人机协作",
}

_GATE_LABELS = {
    "boot": "启动",
    "core_tasks": "核心任务",
    "security": "高危安全",
    "persistence": "数据持久化",
}

_SEV_STYLE = {
    "critical": ("#A32D2D", "#FCEBEB", "阻断"),
    "major": ("#854F0B", "#FAEEDA", "严重"),
    "minor": ("#185FA5", "#E6F1FB", "轻微"),
}


def render_html(report: EvaluationReport) -> str:
    """Render an EvaluationReport to a standalone HTML string."""
    # dimension_scores: Dict[str, DimensionScore] -> flat Dict[str, float]
    dims = {k: v.score for k, v in report.dimension_scores.items()}
    radar = _radar_svg(dims)
    gates = _gates_html(report)
    findings = _findings_html(report)
    evidence = _evidence_html(report)

    score_color = "#0F6E56" if report.status == "accepted" else "#A32D2D"
    status_label = {"accepted": "通过评测", "gated": "被硬门槛拦截",
                    "error": "评测异常"}.get(report.status, report.status)
    status_color = {"accepted": "#0F6E56", "gated": "#A32D2D",
                    "error": "#854F0B"}.get(report.status, "#444")

    return _TEMPLATE.format(
        work_id=html.escape(report.work_id),
        title=html.escape(report.config.get("title", report.work_id)),
        created_at=_fmt_time(report.created_at),
        score=f"{report.weighted_score:.1f}",
        score_color=score_color,
        status_label=status_label,
        status_color=status_color,
        radar=radar,
        dim_rows=_dim_rows_html(dims),
        gates=gates,
        findings=findings,
        findings_count=len(report.findings),
        evidence=evidence,
        evidence_count=len(report.evidence),
        reviewers=_reviewers_html(report),
    )


def _fmt_time(epoch: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _radar_svg(dims: Dict[str, float]) -> str:
    """Eight-axis radar chart as inline SVG (no JS)."""
    labels = list(_DIM_LABELS.keys())
    n = len(labels)
    cx, cy, R = 190, 190, 130

    def pt(i: int, val: float) -> str:
        ang = -math.pi / 2 + i * 2 * math.pi / n
        r = R * max(0.0, min(val, 100.0)) / 100.0
        return f"{cx + r * math.cos(ang):.1f},{cy + r * math.sin(ang):.1f}"

    # grid rings
    rings = "".join(
        f'<polygon points="{" ".join(pt(i, v) for i in range(n))}" '
        f'fill="none" stroke="#D3D1C7" stroke-width="0.5"/>'
        for v in (25, 50, 75, 100))

    spokes = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{pt(i, 100).split(",")[0]}" '
        f'y2="{pt(i, 100).split(",")[1]}" stroke="#D3D1C7" '
        f'stroke-width="0.5"/>' for i in range(n))

    data = "".join(
        f'<polygon points="{" ".join(pt(i, dims.get(l, 0)) for i, l in enumerate(labels))}" '
        f'fill="rgba(31,122,77,0.18)" stroke="#0F6E56" stroke-width="2"/>')

    labs = ""
    for i, key in enumerate(labels):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        lx = cx + (R + 26) * math.cos(ang)
        ly = cy + (R + 26) * math.sin(ang)
        anchor = "middle"
        if math.cos(ang) > 0.3:
            anchor = "start"
        elif math.cos(ang) < -0.3:
            anchor = "end"
        val = dims.get(key, 0)
        labs += (f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                 f'font-size="12" fill="#444441" dominant-baseline="central">'
                 f'{_DIM_LABELS[key]} <tspan fill="#888780">{val:.0f}</tspan></text>')

    return (f'<svg viewBox="0 0 380 380" width="380" height="380" '
            f'role="img" aria-label="八维质量雷达图">{rings}{spokes}{data}{labs}</svg>')


def _dim_rows_html(dims: Dict[str, float]) -> str:
    rows = []
    for key, label in _DIM_LABELS.items():
        v = dims.get(key, 0.0)
        color = ("#0F6E56" if v >= 75 else "#BA7517" if v >= 50
                 else "#A32D2D")
        rows.append(
            f'<tr><td class="dl">{label}</td>'
            f'<td class="dv" style="color:{color}">{v:.1f}</td>'
            f'<td class="dbar"><div class="bar"><div class="bar-fill" '
            f'style="width:{v:.1f}%;background:{color}"></div></div></td></tr>')
    return "".join(rows)


def _gates_html(report: EvaluationReport) -> str:
    cells = []
    for g in report.gates:
        label = _GATE_LABELS.get(g.name, g.name)
        if g.passed:
            cls, txt = "gate pass", "✓ 通过"
        else:
            cls, txt = "gate fail", "✗ 拦截"
        reason = html.escape(g.reason) if g.reason else ""
        cells.append(f'<div class="{cls}"><div class="gl">{label}</div>'
                     f'<div class="gs">{txt}</div>'
                     f'<div class="gr">{reason}</div></div>')
    return "".join(cells)


def _findings_html(report: EvaluationReport) -> str:
    ev_index = {e.id: e for e in report.evidence}
    items = []
    for f in report.findings:
        color, bg, sev_label = _SEV_STYLE.get(
            f.severity, ("#444441", "#F1EFE8", f.severity))
        evs = []
        for eid in f.evidence_ids:
            ev = ev_index.get(eid)
            if ev:
                evs.append(f'<a href="#{eid}" class="evlink">`{eid}`</a>')
            else:
                evs.append(f'<span class="evlink bad">`{eid}` 未解析</span>')
        ev_html = "、".join(evs) if evs else '<span class="dim">（无证据引用）</span>'
        items.append(
            f'<li class="finding">'
            f'<div class="fh"><span class="sev" style="color:{color};'
            f'background:{bg}">{sev_label}</span>'
            f'<span class="dim-tag">{html.escape(f.dimension)}</span>'
            f'<span class="ft">{html.escape(f.title)}</span></div>'
            f'<div class="fd">{html.escape(f.detail)}</div>'
            f'<div class="fe">证据：{ev_html}</div></li>')
    if not items:
        return '<p class="dim">未发现缺陷。</p>'
    return '<ul class="flist">' + "".join(items) + "</ul>"


def _evidence_html(report: EvaluationReport) -> str:
    rows = []
    for e in report.evidence:
        rows.append(
            f'<tr id="{e.id}"><td class="mono">{e.id}</td>'
            f'<td>{html.escape(e.kind)}</td>'
            f'<td>{html.escape(e.source)}</td>'
            f'<td>{html.escape(e.summary)}</td>'
            f'<td class="mono small">{e.digest}</td></tr>')
    return "".join(rows)


def _reviewers_html(report: EvaluationReport) -> str:
    if not report.reviewers:
        return '<span class="dim">未记录评审器</span>'
    return " ".join(
        f'<span class="rvtag">{html.escape(str(r))}</span>'
        for r in report.reviewers)


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>EviVibe 评测报告 — {work_id}</title>
<style>
:root{{--fg:#2C2C2A;--mut:#5F5E5A;--bd:#D3D1C7;--bg:#FFFFFF;--soft:#F1EFE8;}}
*{{box-sizing:border-box}}
body{{margin:0;padding:24px;font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:var(--fg);background:var(--soft);}}
.wrap{{max-width:960px;margin:0 auto;background:var(--bg);border:1px solid var(--bd);border-radius:16px;padding:32px;}}
h1{{font-size:20px;margin:0 0 4px;font-weight:500}}
h2{{font-size:15px;margin:32px 0 12px;font-weight:500;border-bottom:1px solid var(--bd);padding-bottom:8px}}
.sub{{color:var(--mut);font-size:13px}}
.hero{{display:flex;gap:32px;align-items:flex-start;flex-wrap:wrap;margin-top:20px}}
.score{{text-align:center;min-width:140px}}
.score .num{{font-size:56px;font-weight:500;line-height:1}}
.score .lbl{{color:var(--mut);font-size:12px;margin-top:6px}}
.status{{display:inline-block;margin-top:10px;padding:3px 12px;border-radius:999px;font-size:12px;font-weight:500}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{padding:8px 10px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}}
th{{color:var(--mut);font-weight:500;font-size:12px}}
.dl{{white-space:nowrap}}
.dv{{text-align:right;font-weight:500;width:56px}}
.dbar{{width:100%}}
.bar{{height:8px;background:var(--soft);border-radius:4px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:4px}}
.gates{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.gate{{border:1px solid var(--bd);border-radius:10px;padding:12px;font-size:13px}}
.gate.pass{{border-color:#9FE1CB;background:#E1F5EE}}
.gate.fail{{border-color:#F7C1C1;background:#FCEBEB}}
.gl{{color:var(--mut);font-size:12px}}
.gs{{font-weight:500;margin:4px 0}}
.gate.pass .gs{{color:#0F6E56}}
.gate.fail .gs{{color:#A32D2D}}
.gr{{color:var(--mut);font-size:12px}}
.flist{{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:14px}}
.finding{{border:1px solid var(--bd);border-radius:10px;padding:14px}}
.fh{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px}}
.sev{{font-size:11px;font-weight:500;padding:2px 8px;border-radius:999px}}
.dim-tag{{font-size:11px;color:var(--mut);border:1px solid var(--bd);border-radius:999px;padding:2px 8px}}
.ft{{font-weight:500;font-size:13px}}
.fd{{color:var(--fg);font-size:13px;line-height:1.6;margin-bottom:8px}}
.fe{{font-size:12px;color:var(--mut)}}
.evlink{{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#185FA5;text-decoration:none}}
.evlink.bad{{color:#A32D2D}}
.mono{{font-family:ui-monospace,Consolas,monospace;font-size:11px}}
.small{{font-size:10px;color:var(--mut)}}
.dim{{color:var(--mut)}}
.rvtag{{display:inline-block;background:var(--soft);border:1px solid var(--bd);border-radius:6px;padding:4px 10px;font-size:12px;color:var(--mut);margin:0 8px 8px 0}}
footer{{margin-top:32px;padding-top:16px;border-top:1px solid var(--bd);color:var(--mut);font-size:12px;text-align:center}}
</style></head>
<body><div class="wrap">
<h1>EviVibe 评测报告 · {work_id}</h1>
<div class="sub">{title} · 生成时间 {created_at}</div>

<div class="hero">
<div class="score">
<div class="num" style="color:{score_color}">{score}</div>
<div class="lbl">加权总分 / 100</div>
<span class="status" style="background:{status_color}1A;color:{status_color}">{status_label}</span>
</div>
<div>{radar}</div>
<div style="flex:1;min-width:260px">
<table>
<thead><tr><th>维度</th><th style="text-align:right">得分</th><th></th></tr></thead>
<tbody>{dim_rows}</tbody>
</table>
</div>
</div>

<h2>硬门槛（任一不过则总分归零）</h2>
<div class="gates">{gates}</div>

<h2>缺陷清单 · {findings_count} 项</h2>
{findings}

<h2>评审器</h2>
<div>{reviewers}</div>

<h2>证据池 · {evidence_count} 条</h2>
<table>
<thead><tr><th>ID</th><th>类型</th><th>来源</th><th>摘要</th><th>摘要摘要</th></tr></thead>
<tbody>{evidence}</tbody>
</table>

<footer>由 EviVibe 生成 — 面向 Vibe Coding 作品的证据绑定评测框架 ·
本报告完全离线，不加载任何外部资源</footer>
</div></body></html>"""


def write_html(report: EvaluationReport, path: str) -> str:
    """Render and write the HTML report, returning the path."""
    html_str = render_html(report)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_str)
    return path
