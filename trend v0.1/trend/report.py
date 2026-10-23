"""终端输出 + HTML 报告"""
import os
from datetime import datetime
from collections import OrderedDict
from trend.config import PROJECT_DIR


def print_block(title, data, col_fmt, report_sections):
    """终端输出 ROC+ID 双列，同时收集数据用于 HTML"""
    print(f"\n  {title}")
    print(f"  {'#':<3s} {'名称':<10s} {'ROC':>8s}  {'ID':>7s}")
    print(f"  {'-'*32}")
    for r in data:
        id_val = r.get("id")
        id_str = f"{id_val:.3f}" if id_val is not None else "     -"
        print(f"  {col_fmt.format(**r)}  {id_str}")
    report_sections.append((title, data))


def write_html(sections, periods=(20, 60, 120)):
    """生成分组 HTML：行业/概念/ETF/个股，每板块先 ROC 后 ID"""
    groups = OrderedDict()
    for title, data in sections:
        parts = title.rsplit("  ", 1)
        if len(parts) != 2:
            continue
        cat, rest = parts
        if rest.startswith("ROC"):
            rank_type, period = "roc", int(rest[3:])
        elif rest.startswith("ID"):
            rank_type, period = "id", int(rest[2:])
        else:
            continue
        if cat not in groups:
            groups[cat] = {"roc": {}, "id": {}}
        groups[cat][rank_type][period] = data

    has_code = lambda cat: any(kw in cat for kw in ("个股", "ETF"))

    cards = []
    for cat, content in groups.items():
        show_code = has_code(cat)
        roc_html = _period_tables(content["roc"], periods, show_code)
        id_html = _period_tables(content["id"], periods, show_code)
        cards.append(
            f'<div class="card"><div class="card-title">{_esc(cat)}</div>'
            f'<div class="card-body">'
            f'<div class="rank-section">'
            f'<div class="section-label"><span class="dot dot-roc"></span>ROC 动量</div>'
            f'<div class="card-tables">{roc_html}</div></div>'
            f'<div class="rank-section">'
            f'<div class="section-label"><span class="dot dot-id"></span>ID 强度</div>'
            f'<div class="card-tables">{id_html}</div></div>'
            f'</div></div>')

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>动量排名 {datetime.now().strftime('%Y-%m-%d')}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh;line-height:1.5}}
.header{{background:linear-gradient(135deg,#0d1117 0%,#161b22 50%,#1a2332 100%);border-bottom:1px solid #30363d;padding:40px 24px 28px;text-align:center}}
.header h1{{font-size:26px;font-weight:700;color:#f0f6fc;letter-spacing:-0.3px}}
.header h1 em{{font-style:normal;background:linear-gradient(135deg,#f78166 0%,#f0883e 60%,#e85d04 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.header .sub{{color:#8b949e;margin-top:6px;font-size:13px}}
.container{{max-width:1300px;margin:0 auto;padding:20px 24px 40px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;margin-bottom:20px;overflow:hidden}}
.card-title{{font-size:16px;font-weight:600;padding:14px 20px;background:#1c2128;border-bottom:1px solid #30363d;color:#e6edf3}}
.card-body{{padding:0}}
.rank-section{{padding:14px 20px;border-bottom:1px solid #1c2128}}
.rank-section:last-child{{border-bottom:none}}
.section-label{{font-size:12px;font-weight:600;color:#8b949e;margin-bottom:10px;display:flex;align-items:center;gap:6px;text-transform:uppercase;letter-spacing:0.5px}}
.dot{{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0}}
.dot-roc{{background:#3fb950;box-shadow:0 0 6px rgba(63,185,80,0.4)}}
.dot-id{{background:#d2a8ff;box-shadow:0 0 6px rgba(210,168,255,0.4)}}
.card-tables{{display:flex;flex-wrap:wrap;gap:10px}}
.table-wrap{{flex:1;min-width:200px;max-width:360px}}
.period-label{{font-size:11px;font-weight:600;color:#58a6ff;margin-bottom:5px;display:inline-block;background:rgba(88,166,255,0.1);padding:2px 8px;border-radius:3px;border:1px solid rgba(88,166,255,0.2)}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;table-layout:auto}}
thead th{{background:#1c2128;color:#8b949e;font-weight:600;padding:6px 8px;text-align:left;border-bottom:2px solid #30363d;position:sticky;top:0;white-space:nowrap}}
thead th:first-child{{width:26px;text-align:center}}
td{{padding:5px 8px;border-bottom:1px solid #1c2128;white-space:nowrap}}
tr:hover td{{background:rgba(88,166,255,0.06)}}
tr:nth-child(even) td{{background:rgba(255,255,255,0.01)}}
.rank{{color:#484f58;text-align:center;font-size:11px;font-weight:600}}
.name{{color:#c9d1d9;overflow:hidden;text-overflow:ellipsis;max-width:110px}}
.code{{color:#8b949e;font-size:11px;font-family:'SF Mono','Cascadia Code','Consolas',monospace}}
.ind{{font-size:11px;overflow:hidden;text-overflow:ellipsis;max-width:70px;border-radius:3px;padding:1px 5px;font-weight:500}}
.ind-top{{background:rgba(88,166,255,0.18);color:#58a6ff;border:1px solid rgba(88,166,255,0.25)}}
.ind-sub{{color:#484f58}}
.roc{{text-align:right;font-weight:600;font-variant-numeric:tabular-nums}}
.roc-up{{color:#3fb950}}.roc-down{{color:#f85149}}.roc-none{{color:#484f58}}
.id{{text-align:right;color:#d2a8ff;font-variant-numeric:tabular-nums;font-size:12px}}
.footer{{text-align:center;padding:20px;color:#484f58;font-size:11px;border-top:1px solid #21262d}}
@media(max-width:900px){{.card-tables{{flex-direction:column}}.table-wrap{{max-width:100%}}}}
</style>
</head>
<body>
<div class="header">
<h1><em>ROC</em> 动量排名报告</h1>
<p class="sub">东方财富 · 行业·概念·沪深A股·ETF</p>
<p class="sub">{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>
<div class="container">
{''.join(cards)}
</div>
<div class="footer">Powered by EastMoney · Trend v0.1 | {datetime.now().strftime('%Y')}</div>
</body>
</html>"""

    report_dir = os.path.join(PROJECT_DIR, "report")
    os.makedirs(report_dir, exist_ok=True)
    fname = os.path.join(report_dir, f"{datetime.now().strftime('%Y-%m-%d_%H%M')}.html")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n报告: {fname}")


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;")


def _roc_class(v):
    if v is None:
        return "roc-none"
    return "roc-up" if v > 0 else "roc-down"


def _period_tables(data_by_period, periods, show_code=False):
    parts = []
    for p in periods:
        data = data_by_period.get(p, [])
        rows = ""
        has_ind = show_code and any(r.get("industry") for r in data)

        # 找出出现最多的行业
        top_ind = None
        if has_ind:
            from collections import Counter
            ind_counts = Counter(r.get("industry", "") for r in data if r.get("industry"))
            if ind_counts:
                top_ind = ind_counts.most_common(1)[0][0]

        for r in data:
            name = _esc(r.get("name", r.get("code", "")))
            code = r.get("code", "")
            ind = _esc(r.get("industry", ""))[:6] if has_ind else ""
            rc = _roc_class(r.get("roc"))
            roc_str = f"{r['roc']:+.1%}" if r.get("roc") is not None else "-"
            id_str = f"{r['id']:.3f}" if r.get("id") is not None else "-"
            code_cell = f'<td class="code">{code}</td>' if show_code and code else ""
            if has_ind and ind:
                ind_cls = "ind ind-top" if ind == top_ind else "ind ind-sub"
                ind_cell = f'<td class="{ind_cls}">{ind}</td>'
            else:
                ind_cell = ""
            rows += (
                f'<tr><td class="rank">{r.get("rank","")}</td>'
                f'{code_cell}'
                f'<td class="name">{name}</td>'
                f'{ind_cell}'
                f'<td class="roc {rc}">{roc_str}</td>'
                f'<td class="id">{id_str}</td></tr>')
        name_header = "名称"
        if show_code and has_ind:
            parts.append(
                f'<div class="table-wrap">'
                f'<div class="period-label">{p}日</div>'
                f'<table><thead><tr><th>#</th><th>代码</th><th>{name_header}</th><th>行业</th>'
                f'<th>ROC</th><th>ID</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div>')
        elif show_code:
            parts.append(
                f'<div class="table-wrap">'
                f'<div class="period-label">{p}日</div>'
                f'<table><thead><tr><th>#</th><th>代码</th><th>{name_header}</th>'
                f'<th>ROC</th><th>ID</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div>')
        else:
            parts.append(
                f'<div class="table-wrap">'
                f'<div class="period-label">{p}日</div>'
                f'<table><thead><tr><th>#</th><th>{name_header}</th>'
                f'<th>ROC</th><th>ID</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div>')
    return "".join(parts)
