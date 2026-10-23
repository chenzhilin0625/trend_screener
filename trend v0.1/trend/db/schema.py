"""数据库表结构"""
import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS stock_list (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    market       TEXT NOT NULL DEFAULT '1',
    industry     TEXT,
    listing_date TEXT,
    total_mcap   REAL,
    circ_mcap    REAL,
    pe_static    REAL,
    pe_dynamic   REAL,
    price        REAL,
    change_pct   REAL,
    turnover     REAL,
    volume_ratio REAL,
    update_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sector_list (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    sector_type  TEXT NOT NULL,
    total_mcap   REAL,
    circ_mcap    REAL,
    price        REAL,
    change_pct   REAL,
    stock_count  INTEGER,
    update_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_concept (
    stock_code   TEXT NOT NULL,
    sector_code  TEXT NOT NULL,
    PRIMARY KEY (stock_code, sector_code)
);

CREATE TABLE IF NOT EXISTS stock_daily (
    code         TEXT NOT NULL,
    date         TEXT NOT NULL,
    period       TEXT NOT NULL DEFAULT 'D',
    open         REAL, close REAL, high REAL, low REAL,
    volume       REAL, amount REAL,
    amplitude    REAL, change_pct REAL, turnover REAL,
    PRIMARY KEY (code, date, period)
);

CREATE TABLE IF NOT EXISTS sector_daily (
    code         TEXT NOT NULL,
    date         TEXT NOT NULL,
    period       TEXT NOT NULL DEFAULT 'D',
    open         REAL, close REAL, high REAL, low REAL,
    volume       REAL, amount REAL,
    amplitude    REAL, change_pct REAL, turnover REAL,
    PRIMARY KEY (code, date, period)
);

CREATE TABLE IF NOT EXISTS etf_list (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    market       TEXT NOT NULL DEFAULT '1',
    fund_size    REAL,
    price        REAL,
    change_pct   REAL,
    update_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS etf_daily (
    code         TEXT NOT NULL, date TEXT NOT NULL,
    period       TEXT NOT NULL DEFAULT 'D',
    open         REAL, close REAL, high REAL, low REAL,
    volume       REAL, amount REAL,
    amplitude    REAL, change_pct REAL, turnover REAL,
    PRIMARY KEY (code, date, period)
);

CREATE TABLE IF NOT EXISTS update_log (
    table_name   TEXT PRIMARY KEY,
    last_update  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stock_daily_date ON stock_daily(date);
CREATE INDEX IF NOT EXISTS idx_sector_daily_date ON sector_daily(date);
CREATE INDEX IF NOT EXISTS idx_etf_daily_date ON etf_daily(date);
CREATE INDEX IF NOT EXISTS idx_stock_industry ON stock_list(industry);
CREATE INDEX IF NOT EXISTS idx_sector_type ON sector_list(sector_type);
"""


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(DDL)
    conn.commit()
    conn.close()
