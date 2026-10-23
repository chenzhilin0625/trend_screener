"""数据库表结构（适配 MiniQMT）"""
import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS stock_list (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    market       TEXT NOT NULL DEFAULT '1',
    listing_date TEXT,
    update_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sector_list (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    sector_type  TEXT NOT NULL,
    member_count INTEGER,
    update_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS etf_list (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    market       TEXT NOT NULL DEFAULT '1',
    update_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_daily (
    code         TEXT NOT NULL,
    date         TEXT NOT NULL,
    period       TEXT NOT NULL DEFAULT 'D',
    open         REAL, close REAL, high REAL, low REAL,
    volume       REAL, amount REAL,
    change_pct   REAL,
    PRIMARY KEY (code, date, period)
);

CREATE TABLE IF NOT EXISTS etf_daily (
    code         TEXT NOT NULL,
    date         TEXT NOT NULL,
    period       TEXT NOT NULL DEFAULT 'D',
    open         REAL, close REAL, high REAL, low REAL,
    volume       REAL, amount REAL,
    change_pct   REAL,
    PRIMARY KEY (code, date, period)
);

-- sector_daily 和 etf_daily 共用 stock_daily 结构（DDL 触发时动态创建）
CREATE TABLE IF NOT EXISTS sector_daily (
    code         TEXT NOT NULL,
    date         TEXT NOT NULL,
    period       TEXT NOT NULL DEFAULT 'D',
    open         REAL, close REAL, high REAL, low REAL,
    volume       REAL, amount REAL,
    change_pct   REAL,
    PRIMARY KEY (code, date, period)
);

-- 行业-成分股对照表（持久化，QMT离线也能验证完整性）
CREATE TABLE IF NOT EXISTS sector_member (
    sector_code  TEXT NOT NULL,
    stock_code   TEXT NOT NULL,
    PRIMARY KEY (sector_code, stock_code)
);

CREATE INDEX IF NOT EXISTS idx_stock_daily_date ON stock_daily(date);
CREATE INDEX IF NOT EXISTS idx_sector_daily_date ON sector_daily(date);
CREATE INDEX IF NOT EXISTS idx_etf_daily_date ON etf_daily(date);
CREATE INDEX IF NOT EXISTS idx_sector_type ON sector_list(sector_type);
"""


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(DDL)
    conn.commit()
    conn.close()
