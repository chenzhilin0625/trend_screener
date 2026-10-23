"""数据同步 — MiniQMT 全量更新"""
import time, sqlite3
from datetime import datetime, timedelta
from trend.config import DB_PATH
from trend.source.miniqmt import MiniQMTSource

KLINE_COLS = "code,date,period,open,close,high,low,volume,amount,change_pct"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    return conn


def _write_klines(cur, rows, table):
    cols = KLINE_COLS.split(",")
    placeholders = ",".join("?" * len(cols))
    cur.executemany(
        f"INSERT OR REPLACE INTO {table} (" + KLINE_COLS + ")"
        f" VALUES({placeholders})",
        [tuple(r.get(c, None) for c in cols) for r in rows],
    )


def sync_incremental(verbose=True):
    """增量更新：只下载新日期 + 新股票"""
    t0 = time.time()

    src = MiniQMTSource()
    if not src.is_available():
        print("[sync] MiniQMT 不可用，请确认 QMT 客户端已启动")
        return {}

    if verbose:
        print("[sync] 使用 MiniQMT 本地行情")

    conn = _connect()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    # 增量日期：DB最新日 ~ 今天 + 5天缓冲
    cur.execute("SELECT MAX(date) FROM stock_daily")
    db_latest = cur.fetchone()[0]
    if db_latest:
        inc_start = (datetime.strptime(db_latest, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    else:
        inc_start = "2021-01-01"
    if verbose:
        print(f"[sync] 增量范围: {inc_start} ~ {today}")

    # ======== 个股 ========
    stock_codes = src.fetch_stock_list()
    _refresh_stock_list(cur, stock_codes)
    cur.execute("SELECT DISTINCT code FROM stock_daily")
    existing = {r[0] for r in cur.fetchall()}

    # 已有股票：只更新增量日期
    inc_codes = [(c + ('.SH' if c.startswith(('5','6','9')) else '.SZ'))
                 for c in existing]
    # 新股票：拉全量
    new_codes = [(c + ('.SH' if c.startswith(('5','6','9')) else '.SZ'))
                 for c in stock_codes if c.split('.')[0] not in existing]
    new_pure = [c.split('.')[0] for c in new_codes]

    if verbose:
        print(f"[sync] 增量更新 {len(inc_codes)} 只, 新股票 {len(new_codes)} 只")
    if inc_codes:
        _sync_klines(cur, src, inc_codes, inc_start, today, "stock_daily", verbose)
    if new_codes:
        _sync_klines(cur, src, new_codes, "2021-01-01", today, "stock_daily", verbose)
    conn.commit()

    # ======== ETF ========
    etf_codes = src.fetch_etf_list()
    _refresh_etf_list(cur, etf_codes)
    _sync_klines(cur, src, etf_codes, inc_start, today, "etf_daily", verbose)
    conn.commit()

    # ======== 行业（只重聚增量日期 + 新股票影响的） ========
    if inc_codes or new_codes:
        _resync_sectors(cur, src, inc_start, today)
    conn.commit()

    conn.close()
    elapsed = round(time.time() - t0, 1)
    if verbose:
        print(f"[sync] 完成, 耗时{elapsed}s")
    return {"elapsed": elapsed}


def _resync_sectors(cur, src, start, today):
    """增量重聚行业（只覆盖最近一段日期）"""
    if verbose_local := True:
        pass  # no verbose needed for helper
    # 删旧最近日期
    cur.execute("DELETE FROM sector_daily WHERE date>=?", (start,))
    cur.connection.commit()
    cache = _load_stock_klines(cur.connection, start, today)
    if not cache:
        return
    for label, fetch_fn in [("SW2", src.fetch_sw2_list), ("SW3", src.fetch_sw3_list)]:
        for sw in fetch_fn():
            rows = src.aggregate_sector_klines(sw["code"], cache, start, today, min_coverage=1.0)
            if rows:
                _write_klines(cur, rows, "sector_daily")
        cur.connection.commit()


def _refresh_stock_list(cur, codes):
    """刷新 stock_list（含真实名称）"""
    from xtquant import xtdata
    today = datetime.now().strftime("%Y-%m-%d")
    for code in codes:
        market = "1" if code.endswith(".SH") else "0"
        pure = code.split(".")[0]
        name = pure  # fallback
        try:
            info = xtdata.get_instrument_detail(code)
            if info:
                name = info.get("InstrumentName", pure)
        except Exception:
            pass
        cur.execute(
            "INSERT OR REPLACE INTO stock_list "
            "(code,name,market,update_date) VALUES(?,?,?,?)",
            (pure, name, market, today),
        )


def _refresh_etf_list(cur, codes):
    """刷新 etf_list"""
    today = datetime.now().strftime("%Y-%m-%d")
    for code in codes:
        market = "1" if code.endswith(".SH") else "0"
        pure = code.split(".")[0]
        cur.execute(
            "INSERT OR IGNORE INTO etf_list "
            "(code,name,market,update_date) VALUES(?,?,?,?)",
            (pure, pure, market, today),
        )


def _refresh_sector_list(cur, sectors):
    """写入 sector_list（SW2/SW3 代码）"""
    today = datetime.now().strftime("%Y-%m-%d")
    for s in sectors:
        cur.execute(
            "INSERT OR REPLACE INTO sector_list "
            "(code,name,sector_type,member_count,update_date) "
            "VALUES(?,?,?,?,?)",
            (s["code"], s["name"], s["sector_type"],
             s.get("member_count"), today),
        )


def _sync_klines(cur, src, codes, start, end, table, verbose):
    """批量下载+写入 K线（每批 commit）"""
    total_rows = 0
    batch_size = 100
    conn = cur.connection
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        klines = src.fetch_klines(batch, start, end)
        for code, rows in klines.items():
            pure = code.split(".")[0]
            for r in rows:
                r["code"] = pure
            _write_klines(cur, rows, table)
            total_rows += len(rows)
        conn.commit()
        if verbose and (i // batch_size) % 10 == 0:
            print(f"  [{table}] {min(i+batch_size,len(codes))}/{len(codes)}")
    return total_rows


def _load_stock_klines(conn, start, end):
    """从 DB 读取个股K线，返回 {code: [{date,close,open,high,low,volume,amount}, ...]}"""
    cur = conn.cursor()
    cur.execute(
        "SELECT code,date,close,open,high,low,volume,amount FROM stock_daily "
        "WHERE date>=? AND date<=? ORDER BY code,date",
        (start, end),
    )
    cache = {}
    for code, date, close, open_, high, low, volume, amount in cur.fetchall():
        cache.setdefault(code, []).append({
            "date": date, "close": close,
            "open": open_, "high": high, "low": low,
            "volume": volume, "amount": amount,
        })
    return cache


def is_data_current():
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM stock_daily")
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return False
    return (datetime.now() - datetime.strptime(row[0], "%Y-%m-%d")).days <= 1
