"""数据同步：全量 + 增量更新，自动选择可用数据源"""
import time, sqlite3, os, random
from datetime import datetime, timedelta
from trend.config import DB_PATH, REQUEST_DELAY, MAX_FAIL_BEFORE_BACKOFF, BACKOFF_SLEEP
from trend.source import get_available_source, EastMoneySource
from trend.source.sina import SinaSource

KLINE_COLS = ("code,date,period,open,close,high,low,volume,"
              "amount,amplitude,change_pct,turnover")

_table_cols_cache = {}


def _get_table_cols(cur, table):
    """缓存表列名，避免每次写入都查 PRAGMA"""
    if table not in _table_cols_cache:
        info = cur.execute(f"PRAGMA table_info({table})").fetchall()
        _table_cols_cache[table] = [r[1] for r in info]
    return _table_cols_cache[table]


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    return conn


def _write_klines(cur, rows, table):
    """动态适配表列，只写入实际存在的列"""
    if not rows:
        return
    table_cols = _get_table_cols(cur, table)
    src_cols = KLINE_COLS.split(",")
    cols = [c for c in src_cols if c in table_cols]
    placeholders = ",".join(["?"] * len(cols))
    cur.executemany(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES({placeholders})",
        [tuple(r.get(c, None) for c in cols) for r in rows],
    )


def _get_latest_date(conn, table):
    row = conn.execute(f"SELECT MAX(date) FROM {table}").fetchone()
    return row[0] if row and row[0] else None


def _get_codes(conn, table):
    rows = conn.execute(f"SELECT code FROM {table} ORDER BY code").fetchall()
    return [r[0] for r in rows]


def sync_incremental(verbose=True):
    """增量更新。个股/板块优先东方财富（数据完整），ETF 用新浪。"""
    t0 = time.time()
    result = {"ok": True, "stock_rows": 0, "sector_rows": 0, "etf_rows": 0,
              "stock_fail": 0, "message": "", "elapsed": 0}

    conn = _connect()

    # 探测各数据源可用性
    em = EastMoneySource()
    em_ok = em.is_available()
    sina = SinaSource()
    sina_ok = sina.is_available()

    # 通用源（东方财富不可用时兜底个股）
    fallback = None
    if not em_ok:
        fallback = get_available_source(preferred=["tencent", "sina"])

    # ---- 个股（腾讯 + 新浪互补覆盖）----
    stock_src = em if em_ok else fallback
    if stock_src and stock_src.can_fetch_stocks():
        codes = _get_codes(conn, "stock_list")
        if verbose:
            print(f"[sync] 个股 {len(codes)} 只 (via {stock_src.name})")
        stock_r = _sync_klines(conn, codes, stock_src, "stock_daily", verbose)
        result["stock_rows"] = stock_r["rows"]
        result["stock_fail"] = stock_r["fail"]

        # 腾讯失败代码用新浪补拉
        if stock_r["fail"] > 0 and sina_ok:
            _conn = conn
            api_latest = None
            try:
                rows = sina.fetch_kline(codes[0], days=3)
                if rows and len(rows) > 0:
                    api_latest = rows[-1].get("date", "").replace("-", "")
            except Exception:
                pass
            if api_latest:
                api_date = f"{api_latest[:4]}-{api_latest[4:6]}-{api_latest[6:]}"
                got = {r[0] for r in _conn.execute(
                    f"SELECT code FROM stock_daily WHERE date=?", (api_date,)).fetchall()}
                missing = [c for c in codes if c not in got]
                if missing and len(missing) < len(codes):
                    if verbose:
                        print(f"  [stock_daily] 新浪补拉 {len(missing)} 只遗漏")
                    r2 = _sync_klines(conn, missing, sina, "stock_daily", verbose)
                    result["stock_rows"] += r2["rows"]
                    result["stock_fail"] = len(missing) - (len(missing) - r2["fail"])
    elif verbose:
        print("[sync] 个股 跳过 (无可用数据源)")

    # ---- 板块（仅东方财富支持）----
    if em_ok and em.can_fetch_sectors():
        codes = _get_codes(conn, "sector_list")
        if verbose:
            print(f"[sync] 板块 {len(codes)} 只 (via eastmoney)")
        sec_r = _sync_klines(conn, codes, em, "sector_daily", verbose)
        result["sector_rows"] = sec_r["rows"]
    elif verbose:
        print("[sync] 板块 跳过 (东方财富不可用)")

    # ---- ETF（新浪全覆盖）----
    # 先从东方财富刷新 ETF 列表（list 接口可用）
    if em._http("https://push2.eastmoney.com/webguest/api/qt/clist/get", {
        "po": "1", "np": "1", "fltt": "2", "invt": "2", "fid": "f3",
        "fs": "b:MK0021,b:MK0022,b:MK0023,b:MK0024",
        "fields": "f2,f3,f12,f14", "pn": "1", "pz": "1",
    }, timeout=5, retries=1):
        etfs = em.fetch_etf_list()
        if etfs:
            cur = conn.cursor()
            today = datetime.now().strftime("%Y-%m-%d")
            for e in etfs:
                cur.execute(
                    "INSERT OR REPLACE INTO etf_list "
                    "(code,name,price,change_pct,fund_size,update_date) "
                    "VALUES(?,?,?,?,?,?)",
                    (e["code"], e["name"], e.get("price"),
                     e.get("change_pct"), e.get("fund_size"), today))
            conn.commit()
            if verbose:
                print(f"[sync] ETF 列表 {len(etfs)} 只 (via eastmoney)")
    if sina_ok:
        codes = _get_codes(conn, "etf_list")
        if verbose:
            print(f"[sync] ETF {len(codes)} 只 (via sina)")
        etf_r = _sync_klines(conn, codes, sina, "etf_daily", verbose)
        result["etf_rows"] = etf_r["rows"]
    elif verbose:
        print("[sync] ETF 跳过 (新浪不可用)")

    conn.close()
    result["elapsed"] = round(time.time() - t0, 1)
    if verbose:
        print(f"[sync] 完成 — 耗时{result['elapsed']}s")
    return result


def _sync_klines(conn, codes, src, table, verbose):
    """同步 K 线。跳过已覆盖最新日期的代码。"""
    cur = conn.cursor()
    ok = fail = 0
    total_rows = 0

    # 探测 API 最新日期
    api_latest = src.probe_latest_date()
    if not api_latest and codes:
        try:
            rows = src.fetch_kline(codes[0], days=3)
            if rows and len(rows) > 0:
                date_str = rows[-1].get("date", "")
                if date_str:
                    api_latest = date_str.replace("-", "")
        except Exception:
            pass

    if not api_latest:
        if verbose:
            print(f"  [{table}] API 探测失败")
        return {"rows": 0, "fail": 0}

    # 跳过已有最新日期的代码
    api_date = f"{api_latest[:4]}-{api_latest[4:6]}-{api_latest[6:]}"
    skip_rows = conn.execute(
        f"SELECT code FROM {table} WHERE date=?", (api_date,)
    ).fetchall()
    skip_codes = {r[0] for r in skip_rows}
    remaining = [c for c in codes if c not in skip_codes]

    if not remaining:
        if verbose:
            print(f"  [{table}] 已是最新 ({len(skip_codes)}/{len(codes)})")
        return {"rows": 0, "fail": 0}

    if verbose:
        print(f"  [{table}] {len(remaining)} 只待拉取 "
              f"(已有 {len(skip_codes)}/{len(codes)} 最新)")

    # 拉取（带指数退避防 ban）
    consecutive_fail = 0
    for i, code in enumerate(remaining):
        rows = src.fetch_kline(code, days=5)
        if rows is None or len(rows) == 0:
            fail += 1
            consecutive_fail += 1
            if consecutive_fail >= MAX_FAIL_BEFORE_BACKOFF:
                wait = BACKOFF_SLEEP * (2 ** min(consecutive_fail // MAX_FAIL_BEFORE_BACKOFF - 1, 3))
                if verbose:
                    print(f"  [{table}] 连续失败 {consecutive_fail}, 暂停{wait}s...")
                time.sleep(wait)
            time.sleep(random.uniform(0.05, 0.15))
            continue
        consecutive_fail = 0
        _write_klines(cur, rows, table)
        ok += 1
        total_rows += len(rows)

        if (i + 1) % 500 == 0:
            conn.commit()
            if verbose:
                print(f"  [{table}] {i+1}/{len(remaining)} ok={ok} fail={fail}")

    conn.commit()
    if verbose:
        print(f"  [{table}] ok={ok} fail={fail} +{total_rows}行")
    return {"rows": total_rows, "fail": fail}


def sync_full(verbose=True):
    """全量下载（需要东方财富源）"""
    from trend.db.schema import init_db

    src = get_available_source(preferred=["eastmoney"])
    if not src or not isinstance(src, EastMoneySource):
        print("[sync] 全量下载需要东方财富数据源，当前不可用")
        return

    init_db(DB_PATH)
    conn = _connect()
    cur = conn.cursor()
    t0 = time.time()

    if verbose:
        print("[sync] 全量下载...")

    stocks = src.fetch_code_list()
    if stocks:
        today = datetime.now().strftime("%Y-%m-%d")
        for s in stocks:
            cur.execute(
                "INSERT OR REPLACE INTO stock_list "
                "(code,name,market,industry,listing_date,total_mcap,circ_mcap,"
                "pe_static,pe_dynamic,price,change_pct,turnover,volume_ratio,update_date) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s["code"], s["name"], s["market"], s["industry"],
                 s.get("listing_date"), s["total_mcap"], s["circ_mcap"],
                 s.get("pe_static"), s.get("pe_dynamic"),
                 s.get("price"), s.get("change_pct"), s.get("turnover"),
                 None, today))
        conn.commit()
        if verbose:
            print(f"  [list] {len(stocks)} 只股票")

    sectors = src.fetch_sector_list()
    if sectors:
        today = datetime.now().strftime("%Y-%m-%d")
        for s in sectors:
            cur.execute(
                "INSERT OR REPLACE INTO sector_list "
                "(code,name,sector_type,total_mcap,circ_mcap,price,change_pct,update_date) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (s["code"], s["name"], s["sector_type"],
                 s.get("total_mcap"), s.get("circ_mcap"),
                 s.get("price"), s.get("change_pct"), today))
        conn.commit()
        if verbose:
            print(f"  [list] {len(sectors)} 个板块")

    conn.close()
    if verbose:
        print(f"[sync] 列表刷新完成 {time.time()-t0:.0f}s")

    sync_incremental(verbose=False)


def is_data_current():
    """检查数据是否最新"""
    try:
        conn = _connect()
        db_last = _get_latest_date(conn, "stock_daily")
        conn.close()
        if not db_last:
            return False
        return db_last >= datetime.now().strftime("%Y-%m-%d")
    except Exception:
        return False
