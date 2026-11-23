"""EviVibe local web GUI.

A zero-dependency (stdlib only) local web interface so users never have to
type CLI commands: start it, pick a work, click "evaluate".

    python -m evivibe.gui            # opens browser automatically
    evivibe gui --port 8400

Runs a small local HTTP server; everything stays on this machine.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import threading
import time
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote

from . import __version__, config as config_mod
from .pipeline import evaluate_and_write

_EVAL_LOCK = threading.Lock()
_MAX_UPLOAD = 80 * 1024 * 1024  # 80 MB per archive
_SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv",
              ".pytest_cache", "dist", "build", ".idea", ".vscode"}
_STATE = {
    "base": os.getcwd(),
    "out_dir": None,
    "tasks": None,
}


def _setup(base: str, out_dir: str | None, tasks: str | None) -> None:
    _STATE["base"] = base
    _STATE["out_dir"] = out_dir or os.path.join(base, "evivibe-gui-output")
    _STATE["tasks"] = tasks or os.path.join(base, "data", "tasks")
    os.makedirs(_STATE["out_dir"], exist_ok=True)


def _discover_works() -> list[dict]:
    """Scan the conventional work roots; same skip rules as batch mode."""
    base = _STATE["base"]
    works: list[dict] = []
    for root_name in ("data/works", "works"):
        root = os.path.join(base, root_name)
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if name.startswith(".") or name.startswith("_"):
                continue
            wdir = os.path.join(root, name)
            if not os.path.isdir(wdir):
                continue
            meta = {}
            try:
                with open(os.path.join(wdir, "work.json"),
                          encoding="utf-8") as fh:
                    meta = json.load(fh)
            except (OSError, ValueError):
                continue  # not a valid work; skip
            works.append({
                "id": meta.get("work_id", name),
                "title": meta.get("title", name),
                "dir": wdir.replace("\\", "/"),
                "root": root_name,
                "requirement": (meta.get("requirement") or "")[:120],
            })
    return works


def _import_work(filename: str, payload: bytes) -> dict:
    """Extract an uploaded .zip into works/<name> and add a work.json stub.

    Zero-dependency multipart is avoided: the browser posts the raw bytes and
    puts the filename in the X-Filename header.
    """
    if not payload:
        raise ValueError("空文件")
    if len(payload) > _MAX_UPLOAD:
        raise ValueError("压缩包超过 80 MB 限制")
    stem = os.path.splitext(os.path.basename(filename))[0].strip()
    stem = "".join(c for c in stem if c.isalnum() or c in "-_ .").strip()
    if not stem:
        stem = time.strftime("imported-%Y%m%d-%H%M%S")
    works_root = os.path.join(_STATE["base"], "works")
    os.makedirs(works_root, exist_ok=True)
    target = os.path.join(works_root, stem)
    n = 1
    while os.path.exists(target):
        n += 1
        target = os.path.join(works_root, f"{stem}-{n}")

    try:
        zf = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile:
        raise ValueError("不是有效的 zip 压缩包（请把文件夹右键压缩成 .zip）")

    members = []
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if name.endswith("/"):
            continue
        parts = [p for p in name.split("/") if p not in ("", ".")]
        if not parts or ".." in parts:
            continue
        if any(p in _SKIP_DIRS for p in parts[:-1]):
            continue
        members.append((info, "/".join(parts)))

    # Flatten a single wrapping folder (common when zipping a project dir).
    tops = {m[1].split("/")[0] for m in members}
    strip = len(tops) == 1 and all("/" in m[1] for m in members)

    os.makedirs(target, exist_ok=True)
    extracted = 0
    for info, rel in members:
        if strip and "/" in rel:
            rel = rel.split("/", 1)[1]
        dest = os.path.join(target, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with zf.open(info) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
        extracted += 1
    if not extracted:
        shutil.rmtree(target, ignore_errors=True)
        raise ValueError("压缩包里没有可用的源文件")

    manifest = os.path.join(target, "work.json")
    created_manifest = not os.path.exists(manifest)
    if created_manifest:
        work_id = os.path.basename(target)
        stub = {
            "work_id": work_id,
            "title": stem,
            "author": "imported",
            "ai_tools": [],
            "requirement": "（请补充：这个作品要解决什么问题、有哪些功能要求和约束。"
                           "需求写得越具体，功能维度的评分越准确。）",
            "expert_labels": {"overall": 0, "dimensions": {}, "severe_defects": []},
        }
        with open(manifest, "w", encoding="utf-8") as fh:
            json.dump(stub, fh, ensure_ascii=False, indent=2)

    return {
        "work_id": os.path.basename(target),
        "title": stem,
        "dir": target.replace("\\", "/"),
        "root": "works",
        "requirement": "已导入 %d 个文件" % extracted,
        "created_manifest": created_manifest,
    }


def _eval_one(work_dir: str, static_only: bool = False) -> dict:
    cfg = config_mod.load_config()
    cfg["reviewer_backend"] = "mock"
    if static_only:
        gcfg = cfg.setdefault("gates", {})
        gcfg["require_boot"] = False
        gcfg["require_core_tasks"] = False
    with _EVAL_LOCK:
        report, _j, _m, _h = evaluate_and_write(
            work_dir, _STATE["tasks"], _STATE["out_dir"], cfg)
    return {
        "mode": "static" if static_only else "full",
        "work_id": report.work_id,
        "status": report.status,
        "weighted_score": round(report.weighted_score, 2),
        "findings": [
            {"severity": f.severity, "dimension": f.dimension,
             "title": f.title, "evidence_ids": f.evidence_ids}
            for f in report.findings
        ],
        "gates": [{"name": g.name, "passed": g.passed,
                   "reason": g.reason} for g in report.gates],
        "dimension_scores": {
            k: round(v.score, 1)
            for k, v in report.dimension_scores.items()},
        "html_url": f"/report/{report.work_id}.html",
    }


class _Handler(BaseHTTPRequestHandler):

    # ---- helpers -------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def log_message(self, *args) -> None:  # quiet default access log
        pass

    # ---- GET -----------------------------------------------------------
    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, _PAGE.encode("utf-8"),
                       "text/html; charset=utf-8")
        elif self.path == "/api/works":
            self._json({"works": _discover_works(),
                        "tasks": _STATE["tasks"].replace("\\", "/")})
        elif self.path.startswith("/api/probe"):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            wdir = q.get("dir", [""])[0]
            self._json({"static_recommended":
                        bool(wdir) and os.path.isdir(wdir)
                        and not os.path.isfile(os.path.join(wdir,
                                                            "runtime_trace.json"))})
        elif self.path.startswith("/report/"):
            name = os.path.basename(self.path[len("/report/"):])
            path = os.path.join(_STATE["out_dir"], name)
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    self._send(200, fh.read(),
                               "text/html; charset=utf-8")
            else:
                self._json({"error": "report not found"}, 404)
        else:
            self._json({"error": "not found"}, 404)

    # ---- POST ----------------------------------------------------------
    def do_POST(self) -> None:
        if self.path == "/api/import":
            self._handle_import()
            return
        if self.path != "/api/evaluate":
            self._json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            work_dir = body.get("dir", "")
            static_only = bool(body.get("static_only", False))
        except (ValueError, OSError):
            self._json({"error": "bad request"}, 400)
            return
        if not os.path.isdir(work_dir):
            self._json({"error": f"work dir not found: {work_dir}"}, 400)
            return
        try:
            self._json(_eval_one(work_dir, static_only))
        except Exception as exc:  # surface pipeline errors to the UI
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def _handle_import(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json({"error": "bad request"}, 400)
            return
        if length <= 0 or length > _MAX_UPLOAD:
            self._json({"error": "文件为空或超过 80 MB"}, 400)
            return
        filename = unquote(self.headers.get("X-Filename", "upload.zip"))
        payload = self.rfile.read(length)
        try:
            info = _import_work(filename, payload)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return
        except OSError as exc:
            self._json({"error": f"写入失败: {exc}"}, 500)
            return
        self._json(info)


# ---------------------------------------------------------------------------
_PAGE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>EviVibe 评测台</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f4f6f9; color: #1c2733; }
  header { background: #123f66; color: #fff; padding: 18px 28px; }
  header h1 { margin: 0; font-size: 20px; font-weight: 600; }
  header span { opacity: .75; font-size: 12px; margin-left: 10px; }
  main { max-width: 1080px; margin: 24px auto; padding: 0 16px; }
  h2 { font-size: 15px; color: #40566b; margin: 26px 0 10px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill,
            minmax(300px, 1fr)); gap: 14px; }
  .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
          padding: 16px; box-shadow: 0 1px 2px rgba(16,32,48,.04); }
  .card h3 { margin: 0 0 4px; font-size: 15px; }
  .card .meta { color: #7b8ea3; font-size: 12px; margin-bottom: 8px; }
  .card .req { color: #4a5d70; font-size: 12px; line-height: 1.5;
               margin: 8px 0 12px; min-height: 34px; }
  .card button { padding: 7px 16px; border: 0; border-radius: 6px;
                 background: #1663a8; color: #fff; font-size: 13px;
                 cursor: pointer; }
  .card button:hover { background: #0f5490; }
  .card button:disabled { background: #a9b8c6; cursor: wait; }
  .result { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
            padding: 20px; margin-top: 10px; }
  .scorebox { display: flex; gap: 26px; align-items: center; flex-wrap: wrap;
              margin-bottom: 12px; }
  .big { font-size: 44px; font-weight: 700; line-height: 1; }
  .big.ok { color: #0e7a52; } .big.gated { color: #b3372f; }
  .badge { padding: 4px 12px; border-radius: 999px; font-size: 12px;
           color: #fff; }
  .badge.ok { background: #0e7a52; } .badge.gated { background: #b3372f; }
  .badge.err { background: #a06a08; }
  .gates { display: flex; gap: 8px; flex-wrap: wrap; margin: 6px 0 14px; }
  .gate { font-size: 12px; padding: 3px 10px; border-radius: 5px;
          border: 1px solid #cbd6e2; }
  .gate.pass { background: #eaf6f0; border-color: #b7dcc7; color: #0e7a52; }
  .gate.fail { background: #fbeceb; border-color: #eeb6b1; color: #b3372f; }
  .dims { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
  .dim { font-size: 12px; background: #eef3f8; padding: 3px 10px;
         border-radius: 5px; }
  .dim b { color: #1663a8; }
  .findings li { font-size: 13px; margin: 5px 0; }
  .sev { display: inline-block; width: 10px; height: 10px; border-radius: 2px;
         margin-right: 6px; }
  .sev.blocker { background: #b3372f; } .sev.critical { background: #c96a1e; }
  .sev.major { background: #a3a12c; } .sev.minor { background: #4a7fb5; }
  iframe { width: 100%; height: 640px; border: 1px solid #e2e8f0;
           border-radius: 8px; margin-top: 14px; background: #fff; }
  .hint { color: #7b8ea3; font-size: 13px; }
  .err { color: #b3372f; }
  .drop { background: #fff; border: 2px dashed #b9c9da; border-radius: 10px;
          padding: 22px; text-align: center; transition: .15s; }
  .drop.over { border-color: #1663a8; background: #eef5fc; }
  .drop p { margin: 0 0 10px; color: #40566b; font-size: 14px; }
  .drop .sub { color: #8fa1b3; font-size: 12px; margin-top: 8px; }
  .drop button { margin-top: 4px; padding: 8px 18px; border: 0;
                 border-radius: 6px; background: #1663a8; color: #fff;
                 font-size: 13px; cursor: pointer; }
  .drop button.ghost { background: #eef3f8; color: #1663a8; margin-left: 8px; }
  .status { font-size: 13px; margin-top: 10px; min-height: 18px; }
  .ok { color: #0e7a52; }
</style>
</head>
<body>
<header>
  <h1>EviVibe 评测台 <span>evidence-bound evaluation · v__VERSION__</span></h1>
</header>
<main>
  <h2>导入新作品（zip 压缩包）</h2>
  <div class="drop" id="drop">
    <p>把源码文件夹压缩成 .zip，拖到这里，或点下面的按钮选择文件</p>
    <input type="file" id="file" accept=".zip" hidden>
    <button id="pick">选择文件</button>
    <button class="ghost" id="pick-eval">导入并立即评测</button>
    <div class="sub">导入后自动解压到 works/ 目录；没有 work.json 会自动生成一份待补充的模板</div>
    <div class="sub">
      <label><input type="checkbox" id="static-only"> 静态体检</label>
      只分析代码，跳过启动与任务门槛，结果仅供参考；纯源码包（没有 runtime_trace.json）建议勾选
    </div>
    <div class="status" id="status"></div>
  </div>

  <h2>选择作品开始评测</h2>
  <div class="cards" id="cards"><div class="hint">正在扫描作品目录…</div></div>
  <h2>评测结果</h2>
  <div class="result" id="result">
    <div class="hint">还没有结果。点击上方卡片里的"开始评测"。</div>
  </div>
</main>
<script>
async function loadWorks() {
  const d = await (await fetch('/api/works')).json();
  const el = document.getElementById('cards');
  if (!d.works || !d.works.length) {
    el.innerHTML = '<div class="hint">没有发现作品。把作品目录放到 ' +
      '<code>data/works/</code> 或 <code>works/</code> 下（需含 work.json）。</div>';
    return;
  }
  el.innerHTML = '';
  for (const w of d.works) {
    const c = document.createElement('div');
    c.className = 'card';
    c.innerHTML = '<h3></h3><div class="meta"></div>' +
      '<div class="req"></div><button>开始评测</button>';
    c.querySelector('h3').textContent = w.title;
    c.querySelector('.meta').textContent =
      w.id + ' · ' + w.root + '/' + w.id;
    c.querySelector('.req').textContent = w.requirement || '';
    const btn = c.querySelector('button');
    btn.onclick = () => runEval(w, btn);
    el.appendChild(c);
  }
}

async function runEval(w, btn) {
  const res = document.getElementById('result');
  btn.disabled = true; btn.textContent = '评测中…';
  res.innerHTML = '<div class="hint">正在评测 ' + w.title + ' …</div>';
  try {
    const r = await (await fetch('/api/evaluate', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({dir: w.dir,
        static_only: document.getElementById('static-only').checked})
    })).json();
    if (r.error) { res.innerHTML = '<div class="err">出错：' + r.error + '</div>'; return; }
    showResult(r);
  } catch (e) {
    res.innerHTML = '<div class="err">请求失败：' + e + '</div>';
  } finally {
    btn.disabled = false; btn.textContent = '开始评测';
  }
}

function showResult(r) {
  const res = document.getElementById('result');
  const status = r.status === 'accepted' ? 'ok' : 'gated';
  const label = r.status === 'accepted' ? '通过评测' :
    (r.status === 'gated' ? '被硬门槛拦截' : r.status);
  let gates = r.gates.map(g =>
    '<span class="gate ' + (g.passed ? 'pass' : 'fail') + '">' +
    g.name + (g.passed ? ' 通过' : ' 拦截') + '</span>').join('');
  let dims = Object.entries(r.dimension_scores).map(([k, v]) =>
    '<span class="dim">' + k + ' <b>' + v + '</b></span>').join('');
  let finds = r.findings.map(f =>
    '<li><span class="sev ' + f.severity + '"></span>[' + f.dimension +
    '] ' + f.title + ' <span class="hint">证据 ' +
    f.evidence_ids.join(', ') + '</span></li>').join('');
  const modeNote = r.mode === 'static'
    ? '<div class="hint" style="color:#a06a08">静态体检：仅分析代码，'
      + '没有验证启动与运行行为，此分数仅供参考，不作为正式评测结论。</div>'
    : '';
  res.innerHTML = modeNote +
    '<div class="scorebox"><div class="big ' + status + '">' +
    r.weighted_score + '</div><span class="badge ' + status + '">' + label +
    '</span><span class="hint">缺陷 ' + r.findings.length + ' 条 · ' +
    '点击下方报告可展开完整证据链</span></div>' +
    '<div class="gates">' + gates + '</div>' +
    '<div class="dims">' + dims + '</div>' +
    (finds ? '<ul class="findings">' + finds + '</ul>' : '') +
    '<iframe src="' + r.html_url + '"></iframe>';
}

loadWorks();

// ---------- import ----------
const drop = document.getElementById('drop');
const fileInput = document.getElementById('file');
const statusEl = document.getElementById('status');
let pendingEval = false;

document.getElementById('pick').onclick = () => { pendingEval = false; fileInput.click(); };
document.getElementById('pick-eval').onclick = () => { pendingEval = true; fileInput.click(); };
fileInput.onchange = () => { if (fileInput.files[0]) upload(fileInput.files[0]); };

['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.add('over');
}));
['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.remove('over');
}));
drop.addEventListener('drop', e => {
  const f = e.dataTransfer.files[0];
  if (f) { pendingEval = true; upload(f); }
});

async function upload(file) {
  if (!/\\.zip$/i.test(file.name)) {
    statusEl.className = 'status err';
    statusEl.textContent = '请上传 .zip 压缩包（文件夹右键 → 压缩为 zip）';
    return;
  }
  statusEl.className = 'status';
  statusEl.textContent = '正在上传 ' + file.name + ' …';
  try {
    const res = await fetch('/api/import', {
      method: 'POST',
      headers: {'X-Filename': encodeURIComponent(file.name)},
      body: file,
    });
    const d = await res.json();
    if (d.error) { statusEl.className = 'status err'; statusEl.textContent = '导入失败：' + d.error; return; }
    statusEl.className = 'status ok';
    statusEl.textContent = '已导入「' + d.title + '」→ works/' + d.work_id +
      (d.created_manifest ? '（已自动生成 work.json，建议先补充需求描述）' : '');
    if (!document.getElementById('static-only').checked) {
      const probe = await (await fetch('/api/probe?dir=' +
        encodeURIComponent(d.dir))).json();
      if (probe.static_recommended) {
        document.getElementById('static-only').checked = true;
        statusEl.textContent += ' · 未检测到运行时证据，已自动切换为静态体检';
      }
    }
    fileInput.value = '';
    await loadWorks();
    if (pendingEval) {
      runEval({id: d.work_id, title: d.title, dir: d.dir}, document.createElement('button'));
    }
  } catch (e) {
    statusEl.className = 'status err';
    statusEl.textContent = '上传出错：' + e;
  }
}
</script>
</body>
</html>
""".replace("__VERSION__", __version__)


def serve(base: str | None = None, port: int = 8400,
          out_dir: str | None = None, tasks: str | None = None,
          open_browser: bool = True) -> None:
    base_dir = base or os.getcwd()
    if not os.path.isdir(os.path.join(base_dir, "data", "works")):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.isdir(os.path.join(repo, "data", "works")):
            base_dir = repo
    _setup(base_dir, out_dir, tasks)
    url = f"http://127.0.0.1:{port}"
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"EviVibe 评测台已启动: {url}")
    print("作品目录: data/works/ 与 works/ · 报告输出: " +
          _STATE["out_dir"].replace("\\", "/"))
    print("关闭此窗口或按 Ctrl+C 退出。")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="evivibe-gui")
    ap.add_argument("--port", type=int, default=8400)
    ap.add_argument("--base", default=None, help="repository root")
    ap.add_argument("--out", default=None, help="report output dir")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    serve(a.base, a.port, a.out, open_browser=not a.no_browser)
