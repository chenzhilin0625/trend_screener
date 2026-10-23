"""
批量下载全量 A 股历史日线数据 —— Baostock 版

特性：
  - 无频率限制，全量 5500 只约 40-60 分钟
  - 断点续传：已下载的股票自动跳过
  - 数据写入与 main.py 完全兼容的 SQLite 表
  - 同时下载大盘指数日线

用法：
  python batch_download.py           # 下载所有股票（断点续传）
  python batch_download.py --reset   # 清空重来
  python batch_download.py --test    # 测试模式（只下10只）
"""

import sqlite3
import time
import sys
import os
from datetime import datetime

import baostock as bs
import pandas as pd

DB_PATH = "trend_data.db"
START_DATE = "2015-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d")

# 深圳主板开头：000, 001, 002, 003；创业板：300, 301
# 上海主板：600, 601, 603, 605；科创板：688, 689
# 北交所：8开头（baostock 用 bj. 前缀，部分可能不支持）

# ---- 数据库初始化 ----

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
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


def get_downloaded_codes(conn):
    """获取已下载的股票代码集合（用于断点续传）。"""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ts_code FROM stock_daily")
    return {r[0] for r in cur.fetchall()}


def get_stock_list():
    """通过 Baostock 获取全市场股票列表。"""
    rs = bs.query_stock_basic()
    if rs.error_code != '0':
        print(f"  query_stock_basic error: {rs.error_msg}")
        return []

    stocks = []
    while rs.next():
        row = rs.get_row_data()
        code_full = row[0]      # sh.600519
        name = row[1]           # 贵州茅台
        status = row[2]         # 1=正常
        if status == '1':
            # 剥出纯数字代码
            if '.' in code_full:
                pure_code = code_full.split('.')[1]
            else:
                pure_code = code_full
            stocks.append((code_full, pure_code, name))

    print(f"  全市场股票: {len(stocks)} 只")
    return stocks


def download_one_stock(conn, code_full, pure_code, name):
    """下载一只股票的完整历史日线，写入 DB。"""
    rs = bs.query_history_k_data_plus(
        code_full,
        "date,open,high,low,close,volume,amount",
        start_date=START_DATE,
        end_date=END_DATE,
        frequency="d",
        adjustflag="2"  # 前复权
    )
    if rs.error_code != '0':
        return 0

    rows = []
    while rs.next():
        row = rs.get_row_data()
        # row: [date, open, high, low, close, volume, amount]
        if row[1] == '' or row[1] == '0.000000':
            continue  # 停牌或无数据日
        rows.append((
            pure_code,         # ts_code
            row[0],            # date
            float(row[1]),     # open
            float(row[2]),     # high
            float(row[3]),     # low
            float(row[4]),     # close
            float(row[5]),     # volume
            float(row[6]),     # amount
        ))

    if not rows:
        return 0

    # 批量写入
    cur = conn.cursor()
    cur.executemany(
        "INSERT OR REPLACE INTO stock_daily VALUES(?,?,?,?,?,?,?,?)",
        rows
    )
    # 写入名称
    cur.execute("INSERT OR REPLACE INTO stock_info VALUES(?,?)",
                (pure_code, name))
    conn.commit()
    return len(rows)


def download_indices(conn):
    """下载大盘指数日线（通过 baostock 的指数接口）。"""
    print("\n  大盘指数...")
    indices = {
        "sh.000300": "000300",   # 沪深300
        "sh.000001": "000001",   # 上证指数
        "sh.000905": "000905",   # 中证500
        "sz.399006": "399006",   # 创业板指
    }
    cur = conn.cursor()
    for code_full, symbol in indices.items():
        rs = bs.query_history_k_data_plus(
            code_full,
            "date,open,high,low,close,volume,amount",
            start_date=START_DATE,
            end_date=END_DATE,
            frequency="d",
            adjustflag="2"
        )
        if rs.error_code != '0':
            print(f"    {symbol}: error {rs.error_msg}")
            continue

        rows = []
        while rs.next():
            row = rs.get_row_data()
            if row[1] == '' or row[1] == '0.000000':
                continue
            rows.append((symbol, row[0], float(row[1]), float(row[2]),
                        float(row[3]), float(row[4]), float(row[5]), float(row[6])))

        if rows:
            cur.executemany(
                "INSERT OR REPLACE INTO index_daily VALUES(?,?,?,?,?,?,?,?)",
                rows
            )
            conn.commit()
            print(f"    {symbol}: {len(rows)} rows")
        else:
            print(f"    {symbol}: no data")


def main():
    print("=" * 60)
    print("  A-Share Batch Downloader (Baostock)")
    print(f"  Date range: {START_DATE} ~ {END_DATE}")
    print("=" * 60)

    reset = "--reset" in sys.argv
    test_mode = "--test" in sys.argv

    if reset:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM stock_daily")
        conn.execute("DELETE FROM stock_info")
        conn.execute("DELETE FROM index_daily")
        conn.execute("DELETE FROM update_log WHERE table_name LIKE 'stock_%' OR table_name LIKE 'index_%'")
        conn.commit()
        conn.close()
        print("[reset] Old stock/index data cleared.")

    # 初始化
    conn = init_db()
    downloaded = get_downloaded_codes(conn)

    # Baostock 登录
    print("\nBaostock login...")
    lg = bs.login()
    if lg.error_code != '0':
        print(f"  Login FAILED: {lg.error_msg}")
        print("  Make sure proxy is OFF and try again.")
        conn.close()
        return
    print(f"  OK: {lg.error_msg}")

    # 获取股票列表
    print("\nGetting stock list...")
    stocks = get_stock_list()
    if test_mode:
        stocks = stocks[:10]
        print("  [TEST MODE] only 10 stocks")

    # 计算待下载量
    remaining = [(f, p, n) for f, p, n in stocks if p not in downloaded]
    print(f"  Already downloaded: {len(downloaded)}")
    print(f"  Remaining: {len(remaining)}")
    est = len(remaining) * 0.5 / 60  # ~0.5s per stock
    print(f"  Estimated time: ~{est:.0f} min")

    if not remaining:
        print("\n  Nothing to download!")
        bs.logout()
        conn.close()
        return

    # 开始批量下载
    print("\n" + "-" * 60)
    print(f"  Downloading {len(remaining)} stocks...")
    print("-" * 60)

    t_start = time.time()
    ok_count = 0
    fail_count = 0
    total_rows = 0

    for i, (code_full, pure_code, name) in enumerate(remaining, 1):
        try:
            n_rows = download_one_stock(conn, code_full, pure_code, name)
            if n_rows > 0:
                ok_count += 1
                total_rows += n_rows
            else:
                fail_count += 1
        except Exception as e:
            fail_count += 1
            if fail_count <= 5:
                print(f"  [!] {code_full} {name}: {e}")

        # 每 50 只打印进度
        if i % 50 == 0:
            elapsed = time.time() - t_start
            rate = i / elapsed * 60  # stocks/min
            eta = (len(remaining) - i) / rate if rate > 0 else 0
            print(f"  [{i}/{len(remaining)}] ok={ok_count} fail={fail_count} "
                  f"rows={total_rows} rate={rate:.0f}/min eta={eta:.0f}min")

        # 每 200 只提交一次确保数据落盘
        if i % 200 == 0:
            print(f"  [checkpoint] data committed at {i}")

    elapsed = time.time() - t_start
    print(f"\n  DONE: {ok_count} ok, {fail_count} failed")
    print(f"  Total rows: {total_rows}")
    print(f"  Time: {elapsed/60:.1f} min")

    # 下载大盘指数
    download_indices(conn)

    # 记录更新
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT OR REPLACE INTO update_log VALUES(?, ?)",
        ("stock_daily_all", today))
    conn.execute(
        "INSERT OR REPLACE INTO update_log VALUES(?, ?)",
        ("index_daily_all", today))
    conn.commit()

    bs.logout()
    conn.close()
    print("\n" + "=" * 60)
    print("  Batch download complete.")
    print(f"  Now run: python main.py --init  (for industry data)")
    print(f"  Then:    python main.py          (daily screening)")
    print("=" * 60)


if __name__ == "__main__":
    main()
