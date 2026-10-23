"""
从通达信本地数据导入行业/板块日线数据

使用 mootdx 读取 880xxx 板块指数日线，
写入 industry_daily 表，与 DataManager 兼容。

用法：
    python tdx_industry_import.py           # 导入全部板块
    python tdx_industry_import.py --test    # 测试模式（仅 10 个）
"""

import sqlite3
import sys
import time
from datetime import datetime

from mootdx.reader import Reader

DB_PATH = "trend_data.db"
TDX_DIR = r"D:\tdx"


def load_board_names():
    """从通达信 tdxzs.cfg 加载板块代码→名称映射。"""
    name_map = {}
    path = f"{TDX_DIR}/T0002/hq_cache/tdxzs.cfg"
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
        print("  [warn] tdxzs.cfg not found, using code as name")
    return name_map


def discover_boards(reader):
    """扫描 880000-881000，返回存在的板块代码列表。"""
    codes = []
    for c in range(880001, 881000):
        try:
            df = reader.daily(symbol=str(c))
            if df is not None and len(df) > 0:
                codes.append(str(c))
        except Exception:
            pass
    return codes


def import_boards(test_mode=False):
    t_start = time.time()
    print("=" * 60)
    print("  TDX Industry Board Importer (via mootdx)")
    print(f"  Source: {TDX_DIR}")
    print("=" * 60)

    # 初始化
    reader = Reader.factory(market="std", tdxdir=TDX_DIR)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")

    # 确保表存在
    conn.executescript("""
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
    """)
    conn.commit()

    # 清旧数据
    conn.execute("DELETE FROM industry_daily")
    conn.commit()

    # 获取板块列表和名称
    boards = discover_boards(reader)
    names = load_board_names()
    print(f"\n  Found {len(boards)} boards")

    if test_mode:
        boards = boards[:10]
        print("  [TEST MODE] only 10 boards")

    # 逐板块导入
    print(f"\n  Importing {len(boards)} boards...")
    cur = conn.cursor()
    total_rows = 0
    ok_count = 0

    for i, code in enumerate(boards):
        name = names.get(code, code)
        try:
            df = reader.daily(symbol=code)
            if df is None or df.empty:
                continue

            # 准备数据
            rows = []
            for idx, row in df.iterrows():
                date_str = idx.strftime("%Y%m%d") if hasattr(idx, "strftime") else str(idx)
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
                    "INSERT OR IGNORE INTO industry_daily VALUES(?,?,?,?,?,?,?,?)",
                    rows,
                )
                ok_count += 1
                total_rows += len(rows)

            if (i + 1) % 100 == 0:
                conn.commit()
                elapsed = time.time() - t_start
                print(f"  [{i + 1}/{len(boards)}] {ok_count} ok, "
                      f"{total_rows:,} rows, {elapsed:.0f}s")

        except Exception as e:
            print(f"  [!] {code} ({name}): {e}")

    conn.commit()

    # 记录更新
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT OR REPLACE INTO update_log VALUES(?, ?)",
        ("industry_daily_tdx", today),
    )
    conn.commit()

    elapsed = time.time() - t_start
    print(f"\n  DONE: {ok_count} boards, {total_rows:,} rows in {elapsed:.1f}s")

    # 统计
    cur.execute("SELECT COUNT(DISTINCT symbol), MIN(date), MAX(date) FROM industry_daily")
    r = cur.fetchone()
    print(f"  industry_daily: {r[0]} symbols, {r[1]} ~ {r[2]}")

    conn.close()
    print("=" * 60)


if __name__ == "__main__":
    test_mode = "--test" in sys.argv
    import_boards(test_mode=test_mode)
