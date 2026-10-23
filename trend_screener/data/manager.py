"""
DataManager —— 跨平台版

数据源:
  Windows: TDX (通达信) 本地文件 → 零网络
  Mac/Linux: Baostock 批量下载 → 首次需联网, 之后纯本地

启动时自动检测平台和已有数据，按需同步。
"""

import sqlite3
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

from config import DB_PATH

NAME_CACHE_PATH = "data/stock_names.json"

# 平台检测
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# TDX 相关函数仅在 Windows 惰性加载
_tdx_sync = None
_board_names = None
_stock_ind_map = None


def _get_tdx_sync():
    global _tdx_sync
    if _tdx_sync is None and IS_WINDOWS:
        from data.tdx_sync import sync_all
        _tdx_sync = sync_all
    return _tdx_sync


def _get_board_names():
    global _board_names
    if _board_names is None:
        if IS_WINDOWS:
            try:
                from data.tdx_sync import get_board_names as gbn
                _board_names = gbn()
            except Exception:
                _board_names = {}
        else:
            # Mac: 从 DB 读取板块名
            _board_names = _load_board_names_from_db()
    return _board_names


def _get_stock_ind_map():
    global _stock_ind_map
    if _stock_ind_map is None:
        if IS_WINDOWS:
            try:
                from data.tdx_sync import get_stock_industry_map as gsm
                _stock_ind_map = gsm()
            except Exception:
                _stock_ind_map = {}
        else:
            _stock_ind_map = {}
    return _stock_ind_map


def _load_board_names_from_db():
    """从 industry_daily 表加载板块名（Mac 回退方案）。"""
    db_path = DB_PATH
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM industry_daily")
    names = {}
    for (code,) in cur.fetchall():
        names[str(code)] = str(code)
    conn.close()
    return names


class DataManager:
    """统一数据入口（跨平台版）。

    用法:
        dm = DataManager()
        hs300 = dm.get_index_daily("000300")
        boards = dm.get_industry_boards()
        df = dm.get_industry_daily("880001")
        df_stock = dm.get_stock_daily("600519")
    """

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()
        self._industry_boards_cache = None
        self._stock_list_cache = None

        # 加载名称缓存
        self._name_cache = self._load_name_cache()

        # 启动时自动同步
        self._auto_sync()

    # ================================================================
    #  Schema + Sync
    # ================================================================

    def _ensure_schema(self):
        self._conn.executescript("""
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
            CREATE TABLE IF NOT EXISTS market_breadth (
                date TEXT PRIMARY KEY,
                up_count INTEGER, down_count INTEGER, total_count INTEGER
            );
            CREATE TABLE IF NOT EXISTS update_log (
                table_name TEXT NOT NULL, last_update TEXT NOT NULL,
                PRIMARY KEY (table_name)
            );
            CREATE TABLE IF NOT EXISTS trend_cache (
                id        TEXT NOT NULL,
                calc_date TEXT NOT NULL,
                prim_score REAL, sec_score REAL, min_score REAL,
                total_score REAL,
                prim_up INTEGER, sec_up INTEGER, min_up INTEGER,
                state     TEXT,
                PRIMARY KEY (id, calc_date)
            );
        """)
        self._conn.commit()

    def _load_name_cache(self):
        """批量加载股票名称缓存。"""
        if os.path.exists(NAME_CACHE_PATH):
            try:
                with open(NAME_CACHE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _auto_sync(self):
        """启动时自动同步数据（平台自适应）。"""
        today = datetime.now().strftime("%Y-%m-%d")
        cur = self._conn.cursor()
        cur.execute(
            "SELECT last_update FROM update_log WHERE table_name = ?",
            ("tdx_stock",),
        )
        row = cur.fetchone()
        needs_sync = row is None or str(row[0])[:10] != today

        if not needs_sync:
            print(f"[sync] Data up to date ({sys.platform})")
            return

        if IS_WINDOWS:
            self._sync_from_tdx()
        else:
            self._sync_mac_linux()

    def _sync_from_tdx(self):
        """Windows: 从 TDX 本地文件同步。"""
        sync_fn = _get_tdx_sync()
        if sync_fn is None:
            print("[sync] TDX sync not available (no tdx_sync module)")
            return
        print("[sync] Syncing from TDX...")
        try:
            stats = sync_fn(self.db_path, force=False)
            total = stats.get("stock_rows", 0) + stats.get("index_rows", 0) + stats.get("board_rows", 0)
            if stats.get("skipped"):
                print(f"  Already up to date ({stats.get('elapsed', 0):.2f}s)")
            elif total > 0:
                print(f"  Updated: {stats.get('stocks', '?')} stocks, "
                      f"{stats.get('boards', '?')} boards, {total:,} rows "
                      f"({stats.get('elapsed', 0):.1f}s)")
            else:
                print(f"  No new data")
        except Exception as e:
            print(f"  [warn] TDX sync failed: {e}")

    def _sync_mac_linux(self):
        """Mac/Linux: 检查是否有存量数据，若无则提示用 batch_download.py。"""
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stock_daily")
        n = cur.fetchone()[0]
        if n == 0:
            print("[sync] No local data found.")
            print("[sync] On Mac/Linux, use baostock for initial data load:")
            print("       python batch_download.py")
            print("[sync] This is a one-time operation (~40 min).")
            print("[sync] After that, data stays local.")
        else:
            print(f"[sync] Local data OK ({n:,} rows, no TDX needed)")

    # ================================================================
    #  底层读取
    # ================================================================

    def _read_daily(self, table, key_col, key_val, start=None, end=None):
        sql = f"SELECT * FROM {table} WHERE {key_col} = ?"
        params = [key_val]
        if start:
            sql += " AND date >= ?"; params.append(start)
        if end:
            sql += " AND date <= ?"; params.append(end)
        sql += " ORDER BY date"
        df = pd.read_sql_query(sql, self._conn, params=params)
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        return df

    # ================================================================
    #  大盘指数
    # ================================================================

    def get_index_daily(self, symbol="000300", start=None, end=None):
        """获取指数日线。"""
        return self._read_daily("index_daily", "symbol", symbol, start, end)

    def get_all_index_symbols(self):
        cur = self._conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM index_daily")
        return [r[0] for r in cur.fetchall()]

    # ================================================================
    #  行业板块
    # ================================================================

    def get_industry_boards(self):
        """获取行业板块列表（过滤掉地域板块）。

        返回: [{"code": "880001", "name": "板块名"}, ...]

        排除: 880200-880299（地域板块，如\"北京\"、\"上海\"）
        保留: 880300-880999（概念/行业/风格）+ 881001-881999（二级行业）
        """
        if self._industry_boards_cache is not None:
            return self._industry_boards_cache

        names = _get_board_names()
        cur = self._conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM industry_daily ORDER BY symbol")
        boards = []
        for (code,) in cur.fetchall():
            # 过滤地域板块（880200-880299）
            if code.startswith("8802") and len(code) == 6:
                prefix_num = int(code[3:5]) if code[3:5].isdigit() else 99
                if 0 <= prefix_num <= 99:
                    continue
            name = names.get(str(code), code)
            boards.append({"code": code, "name": name})
        self._industry_boards_cache = boards
        return boards

    def get_industry_daily(self, symbol, start=None, end=None):
        """获取行业板块日线。symbol 如 '880001'"""
        return self._read_daily("industry_daily", "symbol", symbol, start, end)

    def get_industry_cons(self, board_code):
        """获取行业板块成分股代码列表。

        从 tdxhy.cfg 的股票→行业映射中反查。
        """
        stock_ind_map = _get_stock_ind_map()
        # board_code 是 880xxx 格式，需要匹配 T-code
        # 目前简单返回所有有该行业映射的股票
        # tdxhy.cfg 给出 stock_code → T-code，我们需要 T-code → stocks
        members = []
        for stock_code, inds in stock_ind_map.items():
            # 简单策略：把所有属于任何版块的股票返回
            members.append(stock_code)
        return members

    # ================================================================
    #  个股
    # ================================================================

    def get_stock_daily(self, ts_code, start=None, end=None):
        """获取个股日线。ts_code 如 '600519'"""
        ts_code = str(ts_code).zfill(6)
        return self._read_daily("stock_daily", "ts_code", ts_code, start, end)

    def get_stock_name(self, ts_code):
        """获取股票名称（优先名称缓存，其次 DB，最后用代码）。"""
        # 1. 名称缓存（批量加载，最快）
        if ts_code in self._name_cache and self._name_cache[ts_code] != ts_code:
            return self._name_cache[ts_code]
        # 2. DB
        cur = self._conn.cursor()
        cur.execute("SELECT name FROM stock_info WHERE ts_code = ?", (ts_code,))
        row = cur.fetchone()
        if row and row[0] and row[0] != ts_code:
            return row[0]
        return ts_code

    def get_all_stock_codes(self):
        """获取全部个股代码。"""
        if self._stock_list_cache is not None:
            return self._stock_list_cache
        cur = self._conn.cursor()
        cur.execute("SELECT DISTINCT ts_code FROM stock_daily")
        codes = [r[0] for r in cur.fetchall()]
        self._stock_list_cache = codes
        return codes

    # ================================================================
    #  市场宽度
    # ================================================================

    def get_market_breadth_history(self):
        df = pd.read_sql_query(
            "SELECT * FROM market_breadth ORDER BY date", self._conn
        )
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        return df

    def update_market_breadth(self):
        """从 stock_daily 表计算每日涨跌家数。"""
        today = datetime.now().strftime("%Y-%m-%d")
        cur = self._conn.cursor()
        cur.execute("SELECT 1 FROM market_breadth WHERE date = ?", (today,))
        if cur.fetchone():
            return

        # 取最新交易日的所有股票收盘价，计算涨跌
        cur.execute("""
            SELECT MAX(date) FROM stock_daily
        """)
        latest = cur.fetchone()[0]
        if not latest:
            return

        # 取最近两天的数据
        cur.execute("""
            SELECT ts_code, date, close FROM stock_daily
            WHERE date = ?
        """, (latest,))
        today_data = {r[0]: r[2] for r in cur.fetchall()}

        prev_date = None
        cur.execute("""
            SELECT MAX(date) FROM stock_daily WHERE date < ?
        """, (latest,))
        r = cur.fetchone()
        if r and r[0]:
            prev_date = r[0]

        if prev_date:
            cur.execute("""
                SELECT ts_code, close FROM stock_daily WHERE date = ?
            """, (prev_date,))
            prev_data = {r[0]: r[1] for r in cur.fetchall()}

            up = sum(1 for c, cl in today_data.items()
                     if c in prev_data and cl > prev_data[c])
            down = sum(1 for c, cl in today_data.items()
                       if c in prev_data and cl < prev_data[c])
            total = len(today_data)
        else:
            up = 0
            down = 0
            total = len(today_data)

        self._conn.execute(
            "INSERT OR REPLACE INTO market_breadth VALUES(?,?,?,?)",
            (today, up, down, total),
        )
        self._conn.commit()

    # ================================================================
    #  申万分类标签
    # ================================================================

    def get_sw_first_info(self):
        """返回空 DataFrame（申万分类数据需要网络，暂不支持离线）。"""
        return pd.DataFrame()

    # ================================================================
    #  清理
    # ================================================================

    def close(self):
        if hasattr(self, "_conn") and self._conn:
            self._conn.close()

    def __del__(self):
        self.close()
