"""
趋势筛选器 Web 前端 —— Flask 后端

启动: python server.py
访问: http://localhost:5000
"""

import os
import sys
import re
import json
import subprocess
import threading
import time
from datetime import datetime
from glob import glob

from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# --- 懒加载 DataManager ---
_dm = None

def get_dm():
    global _dm
    if _dm is None:
        from data.manager import DataManager
        _dm = DataManager()
    return _dm

# --- 导入分析器 ---
from analyzer import search_assets, analyze_single, list_analyses, load_analysis

REPORT_DIR = os.path.join(os.path.dirname(__file__), "report")
SCRIPTS = {
    "default":   ["python", "main.py"],
    "full-scan": ["python", "main.py", "--full-scan"],
    "market-only": ["python", "main.py", "--market-only"],
}

_run_status = {"running": False, "mode": "", "start_time": None,
               "progress": "", "error": None}

# ---- Markdown 转 HTML（简版，针对报告格式） ----

def md_to_html(md_text):
    """将 Markdown 报告转为 HTML。只处理报告中的常见元素。"""
    lines = md_text.split("\n")
    html = []
    in_table = False
    table_rows = []

    for line in lines:
        # 标题
        if line.startswith("# "):
            html.append(f'<h1 class="report-h1">{line[2:]}</h1>')
        elif line.startswith("## "):
            html.append(f'<h2 class="report-h2">{line[3:]}</h2>')
        elif line.startswith("### "):
            html.append(f'<h3 class="report-h3">{line[4:]}</h3>')
        # 表格
        elif line.startswith("|"):
            if not in_table:
                in_table = True
                table_rows = []
            # 跳过分隔线（如 |---|）
            if re.match(r'^\|[\s\-:|]+\|$', line):
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]
            table_rows.append(cells)
        else:
            if in_table:
                html.append(_render_table(table_rows))
                in_table = False
                table_rows = []
            # 普通段落
            if line.strip():
                # 粗体处理
                line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                if line.startswith("*"):
                    html.append(f'<p class="report-meta">{line}</p>')
                else:
                    html.append(f'<p>{line}</p>')

    if in_table:
        html.append(_render_table(table_rows))

    return "\n".join(html)


def _render_table(rows):
    if len(rows) < 2:
        return "<table>" + "".join(
            "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
            for r in rows) + "</table>"

    header = rows[0]
    body = rows[1:]
    h = "<table class='report-table'>"
    h += "<thead><tr>" + "".join(f"<th>{c}</th>" for c in header) + "</tr></thead>"
    h += "<tbody>"
    for row in body:
        h += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
    h += "</tbody></table>"
    return h


# ---- 路由 ----

@app.route("/")
def index():
    with open(os.path.join(os.path.dirname(__file__),
                           "templates", "index.html"), "r", encoding="utf-8") as f:
        return render_template_string(f.read())


# ---- API ----

@app.route("/api/run", methods=["POST"])
def api_run():
    global _run_status
    if _run_status["running"]:
        return jsonify({"ok": False, "error": "A run is already in progress"})

    data = request.get_json() or {}
    mode = data.get("mode", "default")
    if mode not in SCRIPTS:
        return jsonify({"ok": False, "error": f"Unknown mode: {mode}"})

    cmd = SCRIPTS[mode]
    _run_status = {"running": True, "mode": mode,
                   "start_time": datetime.now().isoformat(),
                   "progress": "Starting...", "error": None}

    def _run():
        global _run_status
        try:
            _run_status["progress"] = "Syncing data..."
            proc = subprocess.Popen(
                cmd, cwd=os.path.dirname(__file__),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in proc.stdout:
                line = line.strip()
                if "Layer" in line or "sync" in line.lower():
                    _run_status["progress"] = line
            proc.wait()
            if proc.returncode == 0:
                _run_status["progress"] = "Done"
            else:
                _run_status["error"] = f"Exit code {proc.returncode}"
                _run_status["progress"] = "Failed"
        except Exception as e:
            _run_status["error"] = str(e)
            _run_status["progress"] = "Error"
        finally:
            _run_status["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/status")
def api_status():
    return jsonify(_run_status)


@app.route("/api/report/latest")
def api_report_latest():
    """获取最新 Markdown 报告并渲染为 HTML。"""
    today = datetime.now().strftime("%Y-%m-%d")
    # 先找今天的
    path = os.path.join(REPORT_DIR, f"trend_report_{today}.md")
    if not os.path.exists(path):
        # 找最近的一个
        reports = sorted(glob(os.path.join(REPORT_DIR, "trend_report_*.md")),
                         reverse=True)
        if not reports:
            return jsonify({"ok": False, "error": "No reports found"})
        path = reports[0]
    try:
        with open(path, "r", encoding="utf-8") as f:
            md = f.read()
        html = md_to_html(md)
        fname = os.path.basename(path)
        return jsonify({"ok": True, "filename": fname, "html": html})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/report/<filename>")
def api_report_file(filename):
    """获取指定报告。"""
    path = os.path.join(REPORT_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "File not found"})
    try:
        with open(path, "r", encoding="utf-8") as f:
            md = f.read()
        html = md_to_html(md)
        return jsonify({"ok": True, "filename": filename, "html": html})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/reports")
def api_reports_list():
    """列出所有历史报告。"""
    reports = sorted(glob(os.path.join(REPORT_DIR, "trend_report_*.md")),
                     reverse=True)
    result = []
    for r in reports:
        fname = os.path.basename(r)
        # 从文件名提取日期
        date_str = fname.replace("trend_report_", "").replace(".md", "")
        size = os.path.getsize(r)
        result.append({"filename": fname, "date": date_str, "size": size})
    return jsonify({"ok": True, "reports": result})


# ---- 单标分析 API ----

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    if not q:
        return jsonify({"ok": True, "results": []})
    results = search_assets(get_dm(), q)
    return jsonify({"ok": True, "results": results})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    asset_type = data.get("type", "stock")
    if not code:
        return jsonify({"ok": False, "error": "Missing code"})
    if asset_type not in ("stock", "industry"):
        return jsonify({"ok": False, "error": "type must be stock or industry"})
    try:
        result = analyze_single(get_dm(), code, asset_type)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/analyze/history")
def api_analyze_history():
    items = list_analyses()
    return jsonify({"ok": True, "items": items})


@app.route("/api/analyze/history/<filename>")
def api_analyze_history_file(filename):
    data = load_analysis(filename)
    if data is None:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "result": data})


if __name__ == "__main__":
    print(f"\n  Trend Screener Web UI")
    print(f"  http://localhost:5000")
    print(f"  Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
