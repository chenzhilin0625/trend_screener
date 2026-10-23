"""
TDX 本地数据同步器

从通达信 vipdoc + mootdx 同步数据到 trend_data.db。
每次启动时调用 sync_all()，增量更新。

纯本地，零网络依赖。
"""

import sqlite3
import os
import struct
from datetime import datetime

from mootdx.reader import Reader

TDX_DIR = r"D:\tdx"
TDX_VIPDOC = os.path.join(TDX_DIR, "vipdoc")


def _tdx_reader():
    return Reader.factory(market="std", tdxdir=TDX_DIR)


# ================================================================
#  同步参数
# ================================================================

KNOWN_INDICES = {
    "sh000001": "000001", "sh000300": "000300", "sh000016": "000016",
    "sh000688": "000688", "sh000905": "000905", "sh000852": "000852",
    "sz399001": "399001", "sz399005": "399005", "sz399006": "399006",
    "sz399300": "399300",
    "sh000010": "000010", "sh000011": "000011", "sh000012": "000012",
    "sh000015": "000015", "sh000017": "000017",
    "sz399002": "399002", "sz399004": "399004",
    "sz399100": "399100", "sz399101": "399101", "sz399106": "399106",
    "sz399107": "399107", "sz399108": "399108",
}

# ================================================================
#  低层：.day 解析（只用 struct，不依赖 mootdx 的 daily 方法）
# ================================================================

def parse_day_file(filepath):
    """解析 .day 文件 → [(date_str, open, high, low, close, volume, amount), ...]"""
    rows = []
    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except Exception:
        return rows
    if len(data) % 32 != 0:
        return rows
    n = len(data) // 32
    for i in range(n):
        off = i * 32
        rec = data[off:off + 32]
        date_int, op, hi, lo, cl, amt, vol = struct.unpack("<IIIIIfI", rec[:28])
        op /= 100.0
        hi /= 100.0
        lo /= 100.0
        cl /= 100.0
        if hi == 0 and lo == 0 and cl == 0:
            continue
        rows.append((str(date_int), op, hi, lo, cl, float(vol), float(amt)))
    return rows


def _get_code_from_filename(fname):
    basename = os.path.splitext(fname)[0]
    if len(basename) >= 3:
        return basename[:2], basename[2:], basename
    return None, None, basename


# ================================================================
#  同步实现
# ================================================================

def _is_db_fresh(conn, today):
    """快速检查：今天的数据是否已在 DB 中（避免重复扫描 9000+ 文件）。

    两步验证:
      1. update_log 中 tdx_stock 的记录日期 == 今天
      2. stock_daily 中最新日期 >= 今天（抽查 600519 茅台，最快命中）
    两者都满足 → DB 已是最新，跳过全部文件扫描。
    """
    cur = conn.cursor()
    cur.execute("SELECT last_update FROM update_log WHERE table_name = 'tdx_stock'")
    row = cur.fetchone()
    if not row or str(row[0])[:10] != today:
        return False
    cur.execute("SELECT MAX(date) FROM stock_daily WHERE ts_code = '600519'")
    r = cur.fetchone()
    if r and r[0] and r[0] >= today:
        return True
    # 兜底：如果600519不在库中
    cur.execute("SELECT MAX(date) FROM stock_daily")
    r = cur.fetchone()
    return r is not None and r[0] and r[0] >= today


def sync_all(db_path="trend_data.db", force=False):
    """主入口：同步所有数据。增量（除非 force=True）。

    返回: dict 统计信息
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)

    stats = {"stocks": 0, "indices": 0, "boards": 0,
             "stock_rows": 0, "index_rows": 0, "board_rows": 0}

    t0 = datetime.now()
    today = datetime.now().strftime("%Y-%m-%d")

    # 快速跳过：今天数据已在库中 → 直接返回
    if not force and _is_db_fresh(conn, today):
        stats["elapsed"] = (datetime.now() - t0).total_seconds()
        stats["skipped"] = True
        conn.close()
        return stats

    # 1. 个股 + 指数日线
    ss, si, srows, irows = _sync_day_files(conn, force)
    stats["stocks"] = ss
    stats["indices"] = si
    stats["stock_rows"] = srows
    stats["index_rows"] = irows

    # 2. 行业板块日线
    sb, brows = _sync_industry_boards(conn, force)
    stats["boards"] = sb
    stats["board_rows"] = brows

    # 3. 记录同步时间
    for key in ["stock", "index", "board"]:
        conn.execute(
            "INSERT OR REPLACE INTO update_log VALUES(?, ?)",
            (f"tdx_{key}", today),
        )

    conn.commit()
    conn.close()

    elapsed = (datetime.now() - t0).total_seconds()
    stats["elapsed"] = elapsed
    stats["skipped"] = False
    return stats


def _ensure_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stock_daily (
            ts_code   TEXT NOT NULL, date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            PRIMARY KEY (ts_code, date)
        );
        CREATE TABLE IF NOT EXISTS index_daily (
            symbol TEXT NOT NULL, date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            PRIMARY KEY (symbol, date)
        );
        CREATE TABLE IF NOT EXISTS industry_daily (
            symbol TEXT NOT NULL, date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            PRIMARY KEY (symbol, date)
        );
        CREATE TABLE IF NOT EXISTS stock_info (
            ts_code TEXT PRIMARY KEY, name TEXT
        );
        CREATE TABLE IF NOT EXISTS update_log (
            table_name TEXT NOT NULL, last_update TEXT NOT NULL,
            PRIMARY KEY (table_name)
        );
    """)


def _get_db_max_date(conn, table, key_col):
    cur = conn.cursor()
    cur.execute(f"SELECT MAX(date) FROM {table}")
    r = cur.fetchone()
    return r[0] if r and r[0] else None


def _sync_day_files(conn, force):
    """同步 vipdoc/*/lday/*.day → stock_daily + index_daily"""
    cur = conn.cursor()

    stock_count = 0
    index_count = 0
    stock_rows = 0
    index_rows = 0

    db_max = None if force else _get_db_max_date(conn, "stock_daily", "ts_code")

    for market in ["sh", "sz", "bj"]:
        lday = os.path.join(TDX_VIPDOC, market, "lday")
        if not os.path.isdir(lday):
            continue
        for fname in os.listdir(lday):
            if not fname.endswith(".day"):
                continue
            prefix, pure_code, full_code = _get_code_from_filename(fname)

            fpath = os.path.join(lday, fname)
            all_rows = parse_day_file(fpath)
            if not all_rows:
                continue

            # 增量过滤：只保留比 DB 中更新的数据
            if db_max is not None and not force:
                all_rows = [r for r in all_rows if r[0] > db_max]
            if not all_rows:
                continue

            if full_code in KNOWN_INDICES:
                # 指数
                db_sym = KNOWN_INDICES[full_code]
                db_rows = [(db_sym, r[0], r[1], r[2], r[3], r[4], r[5], r[6])
                           for r in all_rows]
                cur.executemany(
                    "INSERT OR REPLACE INTO index_daily VALUES(?,?,?,?,?,?,?,?)",
                    db_rows,
                )
                index_count += 1
                index_rows += len(db_rows)
            elif pure_code and pure_code.isdigit() and len(pure_code) == 6:
                # 个股
                db_rows = [(pure_code, r[0], r[1], r[2], r[3], r[4], r[5], r[6])
                           for r in all_rows]
                cur.executemany(
                    "INSERT OR REPLACE INTO stock_daily VALUES(?,?,?,?,?,?,?,?)",
                    db_rows,
                )
                cur.execute("INSERT OR IGNORE INTO stock_info VALUES(?,?)",
                            (pure_code, pure_code))
                stock_count += 1
                stock_rows += len(db_rows)

                # 每 500 只提交一次
                if stock_count % 500 == 0:
                    conn.commit()

    conn.commit()
    return stock_count, index_count, stock_rows, index_rows


def _sync_industry_boards(conn, force):
    """通过 mootdx 同步行业板块日线 → industry_daily

    扫描范围: 880001-880999 + 881001-881999（含二级行业）
    """
    reader = _tdx_reader()

    boards = []
    for c in range(880001, 881000):
        try:
            df = reader.daily(symbol=str(c))
            if df is not None and len(df) > 0:
                boards.append(str(c))
        except Exception:
            pass
    # 二级行业 881xxx
    for c in range(881001, 882000):
        try:
            df = reader.daily(symbol=str(c))
            if df is not None and len(df) > 0:
                boards.append(str(c))
        except Exception:
            pass

    cur = conn.cursor()
    db_max = None if force else _get_db_max_date(conn, "industry_daily", "symbol")

    board_count = 0
    total_rows = 0

    for code in boards:
        try:
            df = reader.daily(symbol=code)
            if df is None or df.empty:
                continue

            rows = []
            for idx, row in df.iterrows():
                date_str = idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx)
                if db_max is not None and date_str <= db_max:
                    continue
                rows.append((
                    code,
                    date_str,
                    float(row.get("open", 0)),
                    float(row.get("high", 0)),
                    float(row.get("low", 0)),
                    float(row.get("close", 0)),
                    float(row.get("volume", 0)),
                    float(row.get("amount", 0)),
                ))

            if rows:
                cur.executemany(
                    "INSERT OR REPLACE INTO industry_daily VALUES(?,?,?,?,?,?,?,?)",
                    rows,
                )
                board_count += 1
                total_rows += len(rows)

            if board_count % 100 == 0:
                conn.commit()
        except Exception:
            pass

    conn.commit()
    return board_count, total_rows


# ================================================================
#  辅助：板块名称缓存
# ================================================================

_board_name_cache = None


def get_board_names():
    """返回 {880xxx/881xxx: '板块名称'} 映射。

    来源: tdxzs.cfg (一级板块) + tdxzs3.cfg (二级行业)
    """
    global _board_name_cache
    if _board_name_cache is not None:
        return _board_name_cache

    name_map = {}
    # 一级板块名称
    path1 = os.path.join(TDX_DIR, "T0002", "hq_cache", "tdxzs.cfg")
    # 二级行业名称（申万二级）
    path3 = os.path.join(TDX_DIR, "T0002", "hq_cache", "tdxzs3.cfg")

    for path in [path1, path3]:
        try:
            with open(path, "r", encoding="gbk") as f:
                for line in f:
                    parts = line.strip().split("|")
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        code = parts[1].strip()
                        if code.isdigit() and len(code) == 6:
                            name_map[code] = name
        except FileNotFoundError:
            pass

    _board_name_cache = name_map
    return name_map


def get_stock_industry_map():
    """从 tdxhy.cfg 读取股票→行业映射。

    返回: {stock_code: [industry_codes, ...]}
    """
    mapping = {}
    path = os.path.join(TDX_DIR, "T0002", "hq_cache", "tdxhy.cfg")
    try:
        with open(path, "r", encoding="gbk") as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) >= 3 and parts[0] in ("0", "1"):
                    stock_code = parts[1]
                    industry = parts[2]  # T-code like T1001
                    if stock_code not in mapping:
                        mapping[stock_code] = []
                    mapping[stock_code].append(industry)
    except FileNotFoundError:
        pass
    return mapping


def get_industry_constituents():
    """反查：{T_code: [stock_codes, ...]} — 行业→成分股映射。

    用于个股筛选时，只扫描强势行业内的成分股。
    """
    stock_map = get_stock_industry_map()
    ind_map = {}
    for stock, t_codes in stock_map.items():
        for tc in t_codes:
            if tc not in ind_map:
                ind_map[tc] = []
            ind_map[tc].append(stock)
    return ind_map


def get_all_mapped_stock_codes():
    """返回所有有行业分类映射的股票代码（约5600只）。"""
    return list(get_stock_industry_map().keys())
