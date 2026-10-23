"""
通达信本地数据导入器

从 D:\\tdx\\vipdoc 读取 .day 二进制日线文件，
导入到 trend_data.db 中，与 DataManager / batch_download 完全兼容。

用法：
    python tdx_importer.py              # 全部导入
    python tdx_importer.py --stocks     # 仅个股
    python tdx_importer.py --indices    # 仅指数
    python tdx_importer.py --test       # 测试模式（只导前 20 只）
"""

import sqlite3
import struct
import os
import sys
import time
from datetime import datetime

# ---- 配置 ----
TDX_VIPDOC = r"D:\tdx\vipdoc"
DB_PATH = "trend_data.db"

# 已知大盘指数（映射 tdx 代码 -> DB 代码）
KNOWN_INDICES = {
    "sh000001": "000001",   # 上证指数
    "sh000300": "000300",   # 沪深300
    "sh000016": "000016",   # 上证50
    "sh000688": "000688",   # 科创50
    "sh000905": "000905",   # 中证500
    "sh000852": "000852",   # 中证1000
    "sz399001": "399001",   # 深证成指
    "sz399005": "399005",   # 中小100
    "sz399006": "399006",   # 创业板指
    "sz399300": "399300",   # 沪深300(深)
}

# 额外关注的指数（也导入但可能不是主要指数）
EXTRA_INDICES = {
    "sh000010": "000010", "sh000011": "000011", "sh000012": "000012",
    "sh000015": "000015", "sh000017": "000017",
    "sz399002": "399002", "sz399004": "399004",
    "sz399100": "399100", "sz399101": "399101", "sz399106": "399106",
    "sz399107": "399107", "sz399108": "399108",
}

ALL_KNOWN_INDICES = {**KNOWN_INDICES, **EXTRA_INDICES}

# 交易所前缀
EXCHANGE_MAP = {
    "sh": "sh",
    "sz": "sz", 
    "bj": "bj",
}

# ---- 数据库初始化 ----

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS stock_daily (
            ts_code   TEXT NOT NULL,
            date      TEXT NOT NULL,
            open      REAL,
            high      REAL,
            low       REAL,
            close     REAL,
            volume    REAL,
            amount    REAL,
            PRIMARY KEY (ts_code, date)
        );
        CREATE TABLE IF NOT EXISTS index_daily (
            symbol    TEXT NOT NULL,
            date      TEXT NOT NULL,
            open      REAL,
            high      REAL,
            low       REAL,
            close     REAL,
            volume    REAL,
            amount    REAL,
            PRIMARY KEY (symbol, date)
        );
        CREATE TABLE IF NOT EXISTS industry_daily (
            symbol    TEXT NOT NULL,
            date      TEXT NOT NULL,
            open      REAL,
            high      REAL,
            low       REAL,
            close     REAL,
            volume    REAL,
            amount    REAL,
            PRIMARY KEY (symbol, date)
        );
        CREATE TABLE IF NOT EXISTS stock_info (
            ts_code   TEXT PRIMARY KEY,
            name      TEXT
        );
        CREATE TABLE IF NOT EXISTS update_log (
            table_name TEXT NOT NULL,
            last_update TEXT NOT NULL,
            PRIMARY KEY (table_name)
        );
    """)
    conn.commit()
    return conn


# ---- .day 文件解析 ----

def parse_day_file(filepath):
    """解析通达信 .day 文件，返回 [(date_str, open, high, low, close, volume, amount), ...]"""
    rows = []
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except Exception:
        return rows

    if len(data) % 32 != 0:
        return rows

    n = len(data) // 32
    rows = []
    for i in range(n):
        off = i * 32
        rec = data[off:off + 32]
        date_int, op, hi, lo, cl, amt, vol = struct.unpack('<IIIIIfI', rec[:28])
        # 价格除以 100
        op = op / 100.0
        hi = hi / 100.0
        lo = lo / 100.0
        cl = cl / 100.0
        # 日期
        date_str = str(date_int)
        # 跳过无效记录（价格全为0且日期看起来不合理）
        if hi == 0 and lo == 0 and cl == 0:
            continue
        rows.append((date_str, op, hi, lo, cl, float(vol), float(amt)))
    return rows


def get_code_from_filename(filename):
    """从 'sh600519.day' 提取 ('sh', '600519')"""
    basename = os.path.splitext(filename)[0]  # sh600519
    if len(basename) >= 3:
        prefix = basename[:2]   # sh
        code = basename[2:]     # 600519
        return prefix, code, basename  # prefix, pure_code, full_code
    return None, None, basename


# ---- 主导入逻辑 ----

def import_all(stocks_only=False, indices_only=False, test_mode=False):
    t_start = time.time()
    print("=" * 60)
    print("  TongDaXin Data Importer")
    print(f"  Source: {TDX_VIPDOC}")
    print(f"  Target: {DB_PATH}")
    print("=" * 60)

    conn = init_db()

    # 收集所有 .day 文件
    all_files = []
    for market in ["sh", "sz", "bj"]:
        lday_path = os.path.join(TDX_VIPDOC, market, "lday")
        if not os.path.isdir(lday_path):
            print(f"  [skip] {market}/lday not found")
            continue
        for fname in os.listdir(lday_path):
            if fname.endswith(".day"):
                all_files.append((market, lday_path, fname))

    print(f"\n  Found {len(all_files)} .day files total")

    if test_mode:
        all_files = all_files[:20]
        print("  [TEST MODE] only 20 files")

    # 分类：指数 vs 个股
    index_files = []
    stock_files = []
    for market, lday_path, fname in all_files:
        prefix, pure_code, full_code = get_code_from_filename(fname)
        if full_code in ALL_KNOWN_INDICES:
            index_files.append((market, lday_path, fname, pure_code, full_code))
        elif pure_code and pure_code.isdigit() and len(pure_code) == 6:
            stock_files.append((market, lday_path, fname, pure_code, full_code))

    print(f"  Index files: {len(index_files)}")
    print(f"  Stock files: {len(stock_files)}")

    # ---- 导入指数 ----
    if not stocks_only:
        print("\n" + "-" * 40)
        print(f"  Importing {len(index_files)} indices...")
        print("-" * 40)
        cur = conn.cursor()
        idx_count = 0
        for i, (market, lday_path, fname, pure_code, full_code) in enumerate(index_files):
            filepath = os.path.join(lday_path, fname)
            rows = parse_day_file(filepath)
            if not rows:
                continue
            db_symbol = ALL_KNOWN_INDICES.get(full_code, pure_code)
            db_rows = [(db_symbol, r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]
            cur.executemany(
                "INSERT OR REPLACE INTO index_daily VALUES(?,?,?,?,?,?,?,?)",
                db_rows
            )
            idx_count += 1
            if i % 10 == 0:
                conn.commit()
        conn.commit()
        print(f"  Done: {idx_count} indices imported")

    # ---- 导入个股 ----
    if not indices_only:
        print("\n" + "-" * 40)
        print(f"  Importing {len(stock_files)} stocks...")
        print("-" * 40)
        cur = conn.cursor()
        ok_count = 0
        total_rows = 0
        batch = []
        batch_size = 5000  # 攒一批再写

        for i, (market, lday_path, fname, pure_code, full_code) in enumerate(stock_files):
            filepath = os.path.join(lday_path, fname)
            rows = parse_day_file(filepath)
            if not rows:
                continue
            ok_count += 1
            total_rows += len(rows)

            for r in rows:
                batch.append((pure_code, r[0], r[1], r[2], r[3], r[4], r[5], r[6]))

            # 写入基本信息
            cur.execute("INSERT OR REPLACE INTO stock_info VALUES(?,?)", (pure_code, pure_code))

            if len(batch) >= batch_size:
                cur.executemany(
                    "INSERT OR REPLACE INTO stock_daily VALUES(?,?,?,?,?,?,?,?)",
                    batch
                )
                conn.commit()
                batch.clear()

            if (i + 1) % 500 == 0:
                elapsed = time.time() - t_start
                print(f"  [{i + 1}/{len(stock_files)}] "
                      f"{(i+1)/len(stock_files)*100:.1f}%  "
                      f"{total_rows:,} rows  {elapsed:.0f}s")

        # 写剩余
        if batch:
            cur.executemany(
                "INSERT OR REPLACE INTO stock_daily VALUES(?,?,?,?,?,?,?,?)",
                batch
            )
            conn.commit()

        print(f"  Done: {ok_count} stocks, {total_rows:,} rows")

    # ---- 记录更新日志 ----
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute("INSERT OR REPLACE INTO update_log VALUES(?, ?)",
                 ("stock_daily_tdx", today))
    conn.execute("INSERT OR REPLACE INTO update_log VALUES(?, ?)",
                 ("index_daily_tdx", today))
    conn.commit()

    elapsed = time.time() - t_start
    print("\n" + "=" * 60)
    print(f"  Import complete in {elapsed:.1f}s")
    print(f"  Next: python main.py")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    stocks_only = "--stocks" in sys.argv
    indices_only = "--indices" in sys.argv
    test_mode = "--test" in sys.argv

    import_all(stocks_only=stocks_only, indices_only=indices_only, test_mode=test_mode)
