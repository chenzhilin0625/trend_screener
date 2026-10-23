"""Trend v0.1 — ROC 动量排名"""
import os, sys, time
from datetime import datetime, time as dtime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

from trend.config import DB_PATH
from trend.db.loader import DataLoader
from trend.score.indicators import rank_sectors, rank_stocks, rank_etfs
from trend.report import write_html
from trend.sync import sync_incremental, is_data_current


def _should_sync():
    """交易日盘后 + DB 数据过期 → 需要增量更新"""
    now = datetime.now()
    if now.weekday() >= 5:          # 周末跳过
        return False
    if now.time() < dtime(15, 5):   # 收盘前跳过（15:05 后）
        return False
    return not is_data_current()


# ---- 自动增量同步 ----
args = set(sys.argv[1:])
no_sync = "--no-sync" in args

if not no_sync and _should_sync():
    print("[sync] 交易日盘后，开始增量更新...")
    try:
        sync_incremental(verbose=True)
    except Exception as e:
        print(f"[sync] 增量更新失败: {e}")
        print("[sync] 继续使用现有数据运行排名...")
    print()

# ---- 主流程 ----
loader = DataLoader(DB_PATH)
t0 = time.time()
no_report = "--no-report" in args
sectors_only = "--sectors" in args
etf_only = "--etf" in args
top_n = 30
for a in sys.argv[1:]:
    if a.startswith("--top="):
        top_n = int(a.split("=")[1])

# 股票行业映射
stock_df = loader.get_stock_list_df()
stock_info = {}
for _, r in stock_df.iterrows():
    ind = r.get("industry", "")
    if ind and str(ind) != "nan":
        stock_info[str(r["code"])] = str(ind)

print(f"ROC 动量排名  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"DB: {loader.db_path}")


def _make_roc_id_sections(name, periods, get_data_fn):
    """终端输出 + HTML 数据收集"""
    result = []
    for p in periods:
        for rk in ("roc", "id"):
            data = get_data_fn(p, rk)
            label = f"{name}  {rk.upper()}{p}"
            print(f"\n  {label}  Top {len(data)}")
            print(f"  {'-'*40}")
            for r in data:
                nm = r.get("name", r.get("code", ""))
                roc_val = r.get("roc")
                roc_s = f"{roc_val:>+6.1%}" if roc_val is not None else "      -"
                line = f"  {r['rank']:2d}. {nm:<10s} {roc_s}"
                id_val = r.get("id")
                if id_val is not None:
                    line += f"  {id_val:+.3f}"
                print(line)
            result.append((label, data))
    return result


def _make_stock_block(periods, get_data_fn):
    """个股终端输出 + HTML 数据收集"""
    result = []
    for p in periods:
        for rk in ("roc", "id"):
            data = get_data_fn(p, rk)
            label = f"个股  {rk.upper()}{p}"
            print(f"\n  {label}  Top {min(len(data), top_n)}")
            print(f"  {'-'*44}")
            for r in data[:top_n]:
                code = str(r.get("code", ""))
                nm = str(r.get("name", ""))[:8]
                ind = stock_info.get(code, "")[:6]
                roc_val = r.get("roc")
                roc_s = f"{roc_val:>+6.1%}" if roc_val is not None else "      -"
                line = f"  {r['rank']:2d}. {code:<8s} {nm:<8s} {ind:<6s} {roc_s}"
                id_val = r.get("id")
                if id_val is not None:
                    line += f"  {id_val:+.3f}"
                print(line)
            result.append((label, data))
    return result


PERIODS = (20, 60, 120)
sections = []

# ======== 板块 ========
if not etf_only:
    print(f"\n{'='*70}\n  板块动量排名\n{'='*70}")
    for label, stype in [("行业", "industry"), ("概念", "concept")]:
        fn = lambda s=stype: (lambda p, rk: rank_sectors(loader, period=p, top_n=10, sector_type=s, rank_by=rk))
        sections += _make_roc_id_sections(f"{label}板块", PERIODS, fn())
if sectors_only:
    loader.close()
    if not no_report:
        write_html(sections)
    print(f"\n总耗时 {time.time()-t0:.0f}s")
    exit()

# ======== ETF ========
if not sectors_only:
    print(f"\n{'='*70}\n  ETF 动量排名\n{'='*70}")
    sections2 = _make_roc_id_sections("ETF", PERIODS,
        lambda p, rk: rank_etfs(loader, period=p, top_n=10, rank_by=rk))
    if etf_only:
        loader.close()
        if not no_report:
            write_html(sections + sections2)
        print(f"\n总耗时 {time.time()-t0:.0f}s")
        exit()

# ======== 个股 ========
if not sectors_only and not etf_only:
    print(f"\n{'='*70}\n  个股 动量排名\n{'='*70}")
    sections3 = _make_stock_block(PERIODS,
        lambda p, rk: rank_stocks(loader, period=p, top_n=top_n, rank_by=rk))

loader.close()
print(f"\n总耗时 {time.time()-t0:.0f}s\n{'='*70}")

all_sec = sections
if not sectors_only:
    all_sec += sections2
if not sectors_only and not etf_only:
    all_sec += sections3

if not no_report:
    write_html(all_sec)
