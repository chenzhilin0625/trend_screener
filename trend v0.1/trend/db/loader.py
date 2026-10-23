"""SQLite → pandas 数据加载器"""
import sqlite3, os
import pandas as pd


class DataLoader:
    def __init__(self, db_path=None):
        if db_path is None:
            from trend.config import DB_PATH
            db_path = DB_PATH
        if not os.path.isabs(db_path) and not os.path.exists(db_path):
            db_path = os.path.join(os.path.dirname(__file__), "..", "..", db_path)
        self.db_path = os.path.abspath(db_path)
        self._conn = None

    @property
    def conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _read(self, sql, params=None):
        df = pd.read_sql_query(sql, self.conn, params=params)
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        return df

    # ---- 个股 ----
    def load_stock(self, code, start=None, end=None):
        sql = "SELECT * FROM stock_daily WHERE code=? AND period='D'"
        params = [code]
        if start: sql += " AND date>=?"; params.append(start)
        if end:   sql += " AND date<=?"; params.append(end)
        return self._read(sql + " ORDER BY date", params)

    def load_all_stocks(self, start=None, end=None, min_rows=250):
        codes = self.get_all_stock_codes()
        for code in codes:
            df = self.load_stock(code, start, end)
            if df is not None and len(df) >= min_rows:
                yield code, df

    # ---- 板块 ----
    def load_sector(self, code, start=None, end=None):
        sql = "SELECT * FROM sector_daily WHERE code=? AND period='D'"
        params = [code]
        if start: sql += " AND date>=?"; params.append(start)
        if end:   sql += " AND date<=?"; params.append(end)
        return self._read(sql + " ORDER BY date", params)

    def load_all_sector_data(self, sector_type=None, min_rows=250):
        if sector_type:
            rows = self.conn.execute(
                "SELECT code, name FROM sector_list WHERE sector_type=?",
                (sector_type,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT code, name FROM sector_list").fetchall()
        for code, name in rows:
            df = self.load_sector(code)
            if df is not None and len(df) >= min_rows:
                yield code, name, df

    # ---- 指数 ----
    def load_market_index(self, code="000300", start=None, end=None):
        return self.load_sector(code, start, end)

    # ---- ETF ----
    def load_etf(self, code, start=None, end=None):
        sql = "SELECT * FROM etf_daily WHERE code=? AND period='D'"
        params = [code]
        if start: sql += " AND date>=?"; params.append(start)
        if end:   sql += " AND date<=?"; params.append(end)
        return self._read(sql + " ORDER BY date", params)

    def load_all_etfs(self, min_rows=250):
        rows = self.conn.execute("SELECT code FROM etf_list ORDER BY code").fetchall()
        for (code,) in rows:
            df = self.load_etf(code)
            if df is not None and len(df) >= min_rows:
                yield code, df

    # ---- 元数据 ----
    def get_all_stock_codes(self):
        rows = self.conn.execute("SELECT code FROM stock_list ORDER BY code").fetchall()
        return [r[0] for r in rows]

    def get_stock_list_df(self):
        return pd.read_sql_query("SELECT * FROM stock_list ORDER BY code", self.conn)

    def get_sector_list_df(self, sector_type=None):
        sql = "SELECT * FROM sector_list"
        if sector_type:
            sql += " WHERE sector_type=?"
            return pd.read_sql_query(sql + " ORDER BY code", self.conn, params=(sector_type,))
        return pd.read_sql_query(sql + " ORDER BY code", self.conn)

    def get_stock_name(self, code):
        row = self.conn.execute(
            "SELECT name FROM stock_list WHERE code=?", (code,)).fetchone()
        return row[0] if row else code

    def get_etf_name(self, code):
        row = self.conn.execute(
            "SELECT name FROM etf_list WHERE code=?", (code,)).fetchone()
        return row[0] if row else code

    # ---- 概念映射 ----
    def get_concept_members(self, sector_code):
        rows = self.conn.execute(
            "SELECT stock_code FROM stock_concept WHERE sector_code=?",
            (sector_code,)).fetchall()
        return [r[0] for r in rows]

    def get_date_range(self, table="stock_daily"):
        row = self.conn.execute(
            f"SELECT MIN(date), MAX(date) FROM {table}").fetchone()
        return row if row else (None, None)
