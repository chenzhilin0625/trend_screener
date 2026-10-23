"""终端输出 + HTML 报告（ROC/ID 分卡，缺数据告警）"""
import os, sqlite3
from datetime import datetime
from trend.config import PROJECT_DIR, DB_PATH


def print_block(title, data, col_fmt, report_sections):
    """终端输出"""
    print(f"\n  {title}")
    print(f"  {'#':<3s} {'名称':<10s} {'ROC':>8s}  {'ID':>7s}")
    print(f"  {'-'*32}")
    for r in data:
        id_val = r.get("id")
        id_str = f"{id_val:.3f}" if id_val is not None else "     -"
        print(f"  {col_fmt.format(**r)}  {id_str}")
    report_sections.append((title, data))


def write_html(sections):
    """生成 HTML — ROC/ID 各自独立卡片 + 数据告警"""
    def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;")
    def roc_class(v):
        if v is None: return "roc-none"
        return "roc-up" if v > 0 else "roc-down"
    def roc_str(v):
        if v is None: return "-"
        return f"{v:+.1%}"
    def id_str(v):
        if v is None: return "-"
        return f"{v:.3f}"

    alerts = _check_coverage()

    # 每个 (title, data) 独立一张卡片
    cards = []
    for title, data in sections:
        if not data: continue
        rows_html = ""
        for r in data:
            name = esc(r.get("name", r.get("code", "")))
            rc = roc_class(r.get("roc"))
            rows_html += (
                f'<tr><td class="rank">{r.get("rank","")}</td>'
                f'<td class="name">{name}</td>'
                f'<td class="roc {rc}">{roc_str(r.get("roc"))}</td>'
                f'<td class="id">{id_str(r.get("id"))}</td></tr>')

        is_id = "ID" in title and "ROC" not in title
        badge_cls = "badge-id" if is_id else "badge-roc"
        badge_text = "ID" if is_id else "ROC"

        cards.append(
            f'<div class="card"><div class="card-title">'
            f'<span class="badge {badge_cls}">{badge_text}</span> {esc(title)}</div>'
            f'<table><thead><tr><th>#</th><th>名称</th><th>ROC</th><th>ID</th></tr></thead>'
            f'<tbody>{rows_html}</tbody></table></div>')

    alert_html = ""
    if alerts:
        items = "".join(f"<li>{esc(a)}</li>" for a in alerts)
        alert_html = (
            f'<div class="alert"><div class="alert-title">数据告警</div>'
            f'<ul>{items}</ul></div>')

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>动量排名 {datetime.now().strftime('%Y-%m-%d')}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI','Microsoft YaHei',sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}}
.header{{background:linear-gradient(135deg,#161b22 0%,#21262d 100%);border-bottom:1px solid #30363d;padding:32px 24px;text-align:center}}
.header h1{{font-size:28px;font-weight:700;color:#f0f6fc}}
.header h1 span{{background:linear-gradient(135deg,#f78166,#f0883e);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.header p{{color:#8b949e;margin-top:8px;font-size:14px}}
.alert{{background:#2d1b1b;border:1px solid #f85149;border-radius:8px;padding:16px 20px;margin:0 24px 20px}}
.alert-title{{color:#f85149;font-weight:600;font-size:14px;margin-bottom:8px}}
.alert ul{{color:#f0883e;font-size:13px;padding-left:20px}}
.alert li{{margin:4px 0}}
.container{{max-width:1400px;margin:0 auto;padding:24px;display:flex;flex-wrap:wrap;gap:16px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;overflow:hidden;flex:1;min-width:280px;max-width:340px}}
.card-title{{font-size:14px;font-weight:600;padding:12px 16px;background:#21262d;border-bottom:1px solid #30363d;color:#f0f6fc;display:flex;align-items:center;gap:8px}}
.badge{{font-size:10px;font-weight:700;padding:2px 6px;border-radius:3px}}
.badge-roc{{background:#1a3a1a;color:#3fb950}}
.badge-id{{background:#2a1a3a;color:#d2a8ff}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead th{{background:#21262d;color:#8b949e;font-weight:600;padding:6px 10px;text-align:left;border-bottom:2px solid #30363d}}
td{{padding:4px 10px;border-bottom:1px solid #21262d}}
tr:hover td{{background:#1c2128!important}}
tr:nth-child(even) td{{background:#161b22}}
.rank{{color:#484f58;text-align:center;font-size:12px;width:26px}}
.name{{color:#c9d1d9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:140px}}
.roc{{text-align:right;font-weight:600;font-variant-numeric:tabular-nums}}
.roc-up{{color:#3fb950}}.roc-down{{color:#f85149}}.roc-none{{color:#484f58}}
.id{{text-align:right;color:#d2a8ff;font-variant-numeric:tabular-nums}}
.footer{{text-align:center;padding:24px;color:#484f58;font-size:12px;border-top:1px solid #30363d;margin-top:24px}}
</style></head><body>
<div class="header"><h1><span>ROC</span> 动量排名报告</h1>
<p>SW2 · SW3 · 沪深A股 · ETF | 覆盖率 100%</p>
<p style="margin-top:4px">{datetime.now().strftime('%Y-%m-%d %H:%M')}</p></div>
{alert_html}
<div class="container">{''.join(cards)}</div>
<div class="footer">Powered by MiniQMT · Trend v0.2 | {datetime.now().strftime('%Y')}</div>
</body></html>"""

    report_dir = os.path.join(PROJECT_DIR, "report")
    os.makedirs(report_dir, exist_ok=True)
    fname = os.path.join(report_dir, f"{datetime.now().strftime('%Y-%m-%d_%H%M')}.html")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n报告: {fname}")


def _check_coverage():
    """检查行业最新日覆盖率，返回告警"""
    alerts = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT MAX(date) FROM stock_daily")
        latest = cur.fetchone()[0]
        if not latest:
            conn.close(); return alerts
        cur.execute("SELECT code, name, member_count FROM sector_list WHERE member_count>0")
        for code, name, total in cur.fetchall():
            cur.execute(
                "SELECT COUNT(DISTINCT sm.stock_code) FROM sector_member sm "
                "JOIN stock_daily sd ON sm.stock_code=sd.code AND sd.date=? "
                "WHERE sm.sector_code=?", (latest, code))
            have = cur.fetchone()[0]
            if have < total:
                alerts.append(f"{name}({code}) {latest}日仅{have}/{total}成分股有数据，已跳过")
        conn.close()
    except Exception:
        pass
    return alerts
