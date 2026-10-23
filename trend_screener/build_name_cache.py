"""
股票名称缓存生成器 —— 离线批量获取名称

用法: python build_name_cache.py
生成 stock_names.json，DataManager 启动时自动加载。
"""
import json
import sqlite3
import os

DB_PATH = "trend_data.db"
CACHE_PATH = "data/stock_names.json"


def build_cache():
    """从 DB 中提取所有股票代码，尝试获取名称。"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ts_code FROM stock_daily ORDER BY ts_code")
    codes = [r[0] for r in cur.fetchall()]
    conn.close()

    names = {}
    for code in codes:
        # 默认：代码即名称
        names[code] = code

    # 尝试从 TDX tdxhy.cfg 或其他来源补充（当前无本地名称源）
    # 用户可手动编辑 stock_names.json 添加名称

    os.makedirs("data", exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=2)
    print(f"Generated {CACHE_PATH} with {len(names)} stocks")


def load_cache():
    """加载名称缓存。"""
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    build_cache()
