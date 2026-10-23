"""
数据库表结构 —— 基于东方财富 API 数据格式

数据源:
  - 个股列表: push2.eastmoney.com/api/qt/clist/get  (fs=m:0+t:6,...)
  - K 线:     push2his.eastmoney.com/api/qt/stock/kline/get  (klt=101/102/103)
  - 行业板块: push2.eastmoney.com/api/qt/clist/get  (fs=m:90+t:2)
  - 概念板块: push2.eastmoney.com/api/qt/clist/get  (fs=m:90+t:3)

东方财富字段映射:
  个股列表:
    f12  = 股票代码          "600519"
    f14  = 股票名称          "贵州茅台"
    f13  = 市场             0=深圳, 1=上海
    f2   = 最新价
    f3   = 涨跌幅(%)
    f20  = 总市值(元)
    f21  = 流通市值(元)
    f26  = 上市日期          "20201029"
    f100 = 所属行业          "白酒"
    f103 = 所属概念          "茅指数,白酒,HS300,..."(逗号分隔)
    f23  = 市盈率(静)
    f9   = 市盈率(动)
    f24  = 60日涨跌幅(%)
    f25  = 年初至今涨跌幅(%)
    f117 = 换手率(%)
    f10  = 量比
    f152 = 板块类型?          2=行业,3=概念?

  行业/概念板块列表 (m:90+t:2 / m:90+t:3):
    f12  = 板块代码          "BK0476"
    f14  = 板块名称          "银行"
    f2   = 最新点位
    f3   = 涨跌幅(%)
    f20  = 总市值(元)
    f21  = 流通市值(元)

  K线 (个股/板块 共用):
    f51  = 日期              "2026-07-17"
    f52  = 开盘
    f53  = 收盘
    f54  = 最高
    f55  = 最低
    f56  = 成交量(手)
    f57  = 成交额(元)
    f58  = 振幅(%)
    f59  = 涨跌幅(%)
    f60  = 涨跌额
    f61  = 换手率(%)

K线周期:
  klt=101  日线
  klt=102  周线
  klt=103  月线
"""

# ============================================================
# DDL
# ============================================================

DDL = """
-- ============================================================
-- 个股基本信息表
-- 数据源: clist/get?fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_list (
    code         TEXT PRIMARY KEY,          -- 股票代码 f12, "600519"
    name         TEXT NOT NULL,             -- 股票名称 f14
    market       TEXT NOT NULL DEFAULT '1', -- 市场 f13: 1=上海, 0=深圳
    industry     TEXT,                      -- 所属行业 f100, "白酒"
    listing_date TEXT,                      -- 上市日期 f26, "20201029"
    total_mcap   REAL,                      -- 总市值(元) f20
    circ_mcap    REAL,                      -- 流通市值(元) f21
    pe_static    REAL,                      -- 市盈率(静) f23
    pe_dynamic   REAL,                      -- 市盈率(动) f9
    price        REAL,                      -- 最新价 f2
    change_pct   REAL,                      -- 涨跌幅 f3
    turnover     REAL,                      -- 换手率 f117
    volume_ratio REAL,                      -- 量比 f10
    update_date  TEXT NOT NULL              -- 更新时间
);

-- ============================================================
-- 板块(行业/概念)基本信息表
-- 数据源: clist/get?fs=m:90+t:2 (行业) / m:90+t:3 (概念)
-- ============================================================
CREATE TABLE IF NOT EXISTS sector_list (
    code         TEXT PRIMARY KEY,          -- 板块代码 f12, "BK0476"
    name         TEXT NOT NULL,             -- 板块名称 f14
    sector_type  TEXT NOT NULL,             -- 类型: "industry" 或 "concept"
    total_mcap   REAL,                      -- 总市值 f20
    circ_mcap    REAL,                      -- 流通市值 f21
    price        REAL,                      -- 最新点位 f2
    change_pct   REAL,                      -- 涨跌幅 f3
    stock_count  INTEGER,                   -- 成分股数量
    update_date  TEXT NOT NULL              -- 更新时间
);

-- ============================================================
-- 个股 -> 概念板块 关联表
-- 数据源: stock_list.f103 逗号分隔的概念名称
--         通过 sector_list 名称反查 code
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_concept (
    stock_code   TEXT NOT NULL,
    sector_code  TEXT NOT NULL,
    PRIMARY KEY (stock_code, sector_code),
    FOREIGN KEY (stock_code) REFERENCES stock_list(code),
    FOREIGN KEY (sector_code) REFERENCES sector_list(code)
);

-- ============================================================
-- 个股日/周/月 K 线表
-- 数据源: kline/get?secid=1.600519&klt=101
-- ============================================================
CREATE TABLE IF NOT EXISTS stock_daily (
    code         TEXT NOT NULL,             -- 股票代码 f12
    date         TEXT NOT NULL,             -- 日期 f51, "2026-07-17"
    period       TEXT NOT NULL DEFAULT 'D', -- 周期: D=日, W=周, M=月
    open         REAL,                      -- 开盘 f52
    close        REAL,                      -- 收盘 f53
    high         REAL,                      -- 最高 f54
    low          REAL,                      -- 最低 f55
    volume       REAL,                      -- 成交量(手) f56
    amount       REAL,                      -- 成交额(元) f57
    amplitude    REAL,                      -- 振幅(%) f58
    change_pct   REAL,                      -- 涨跌幅(%) f59
    change_amt   REAL,                      -- 涨跌额 f60
    turnover     REAL,                      -- 换手率(%) f61
    PRIMARY KEY (code, date, period)
);

-- ============================================================
-- 板块(行业/概念)日/周/月 K 线表
-- 数据源: kline/get?secid=90.BK0476&klt=101
-- ============================================================
CREATE TABLE IF NOT EXISTS sector_daily (
    code         TEXT NOT NULL,             -- 板块代码 f12, "BK0476"
    date         TEXT NOT NULL,             -- 日期 f51
    period       TEXT NOT NULL DEFAULT 'D', -- 周期: D/W/M
    open         REAL,                      -- 开盘 f52
    close        REAL,                      -- 收盘 f53
    high         REAL,                      -- 最高 f54
    low          REAL,                      -- 最低 f55
    volume       REAL,                      -- 成交量(手) f56
    amount       REAL,                      -- 成交额(元) f57
    amplitude    REAL,                      -- 振幅(%) f58
    change_pct   REAL,                      -- 涨跌幅(%) f59
    change_amt   REAL,                      -- 涨跌额 f60
    turnover     REAL,                      -- 换手率(%) f61 (板块通常无)
    PRIMARY KEY (code, date, period)
);

-- ============================================================
-- 更新日志表（增量更新用）
-- ============================================================
CREATE TABLE IF NOT EXISTS update_log (
    table_name   TEXT PRIMARY KEY,          -- 表名
    last_update  TEXT NOT NULL              -- 最后更新日期
);

-- ============================================================
-- 索引
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_stock_daily_date ON stock_daily(date);
CREATE INDEX IF NOT EXISTS idx_stock_daily_period ON stock_daily(period);
CREATE INDEX IF NOT EXISTS idx_sector_daily_date ON sector_daily(date);
CREATE INDEX IF NOT EXISTS idx_sector_daily_period ON sector_daily(period);
CREATE INDEX IF NOT EXISTS idx_stock_industry ON stock_list(industry);
CREATE INDEX IF NOT EXISTS idx_sector_type ON sector_list(sector_type);
"""


def get_ddl():
    """返回完整 DDL 字符串。"""
    return DDL


def init_db(db_path="trend_data.db"):
    """初始化全新数据库。"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(DDL)
    conn.commit()
    conn.close()
    print(f"[schema] Database initialized: {db_path}")


if __name__ == "__main__":
    init_db()
