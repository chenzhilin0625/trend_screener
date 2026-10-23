"""
东方财富原生 HTTP 接口测试

直接调用 push2his.eastmoney.com 的公开 API，
绕过 akshare/baostock，验证底层接口连通性。

用法:
    python test_eastmoney.py
"""

import os
import time
import json
from datetime import datetime

# 清代理
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"

import requests

# ============================================
# 合约代码映射
# ============================================
# secid = market_code + "." + stock_code
# market_code: 1=上海, 0=深圳
MARKET_MAP = {
    "6": "1",    # 上海主板 600/601/603/605
    "68": "1",   # 科创板
    "0": "0",    # 深圳主板 000/001/002/003
    "3": "0",    # 创业板 300/301
}

def to_secid(code: str) -> str:
    """600519 -> 1.600519, 000001 -> 0.000001"""
    for prefix, market in MARKET_MAP.items():
        if code.startswith(prefix):
            return f"{market}.{code}"
    return f"1.{code}"  # 默认上海

# ============================================
# 测试 1: 个股日线 K 线
# ============================================

def test_kline():
    print("=" * 60)
    print("  测试 1: 个股日线 K 线")
    print("  push2his.eastmoney.com/api/qt/stock/kline/get")
    print("=" * 60)

    test_stocks = {
        "600519": "贵州茅台",
        "000001": "平安银行",
        "300750": "宁德时代",
    }

    base_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    for code, name in test_stocks.items():
        secid = to_secid(code)
        t0 = time.time()
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",        # 101=日线
            "fqt": "1",          # 1=前复权
            "beg": "20250101",
            "end": datetime.now().strftime("%Y%m%d"),
        }

        try:
            resp = requests.get(base_url, params=params, timeout=15)
            data = resp.json()
            rc = data.get("rc")
            if rc != 0:
                print(f"  [FAIL] {code} ({name}): rc={rc}, msg={data.get('message', '?')}")
                continue

            klines = data.get("data", {}).get("klines", [])
            if klines:
                first = klines[0].split(",")
                last = klines[-1].split(",")
                print(f"  [OK] {code} ({name}): {len(klines)} rows, "
                      f"{first[0]} ~ {last[0]}, "
                      f"close={last[2]}, volume={last[5]}, "
                      f"{time.time() - t0:.2f}s")
            else:
                print(f"  [FAIL] {code} ({name}): klines empty")
        except Exception as e:
            print(f"  [FAIL] {code} ({name}): {type(e).__name__}: {e}")


# ============================================
# 测试 2: 指数日线
# ============================================

def test_index():
    print()
    print("=" * 60)
    print("  测试 2: 指数日线")
    print("=" * 60)

    indices = {
        "1.000001": "上证指数",
        "1.000300": "沪深300",
        "0.399006": "创业板指",
        "1.000905": "中证500",
        "1.000688": "科创50",
    }

    base_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    for secid, name in indices.items():
        t0 = time.time()
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "beg": "20250101",
            "end": datetime.now().strftime("%Y%m%d"),
        }
        try:
            resp = requests.get(base_url, params=params, timeout=15)
            data = resp.json()
            rc = data.get("rc")
            if rc != 0:
                print(f"  [FAIL] {name} ({secid}): rc={rc}")
                continue
            klines = data.get("data", {}).get("klines", [])
            if klines:
                last = klines[-1].split(",")
                print(f"  [OK] {name}: {len(klines)} rows, "
                      f"latest {last[0]} close={last[2]}, "
                      f"{time.time() - t0:.2f}s")
            else:
                print(f"  [FAIL] {name}: empty")
        except Exception as e:
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")


# ============================================
# 测试 3: 股票列表
# ============================================

def test_stock_list():
    print()
    print("=" * 60)
    print("  测试 3: 全市场股票列表")
    print("  push2.eastmoney.com/api/qt/clist/get")
    print("=" * 60)

    # fs: 市场筛选
    # m:0+t:6  = 沪A主板    m:0+t:80 = 科创板
    # m:1+t:2  = 深A主板    m:1+t:23 = 创业板
    filters = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"

    base_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": "20",
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": filters,
        "fields": "f2,f3,f4,f5,f6,f12,f13,f14,f15,f16,f17,f18,f20",
    }

    t0 = time.time()
    try:
        resp = requests.get(base_url, params=params, timeout=15)
        data = resp.json()
        rc = data.get("rc")
        total = data.get("data", {}).get("total", 0)
        items = data.get("data", {}).get("diff", [])

        if rc == 0 and items:
            print(f"  [OK] 全市场: {total} 只 (本页 {len(items)} 只), {time.time() - t0:.2f}s")
            for item in items[:5]:
                code = item.get("f12", "")
                name = item.get("f14", "")
                price = item.get("f2", "")
                change_pct = item.get("f3", "")
                print(f"       {code} {name}  最新{price}  涨跌{change_pct}%")
            print(f"       ... (共 {total} 只)")
        else:
            print(f"  [FAIL] rc={rc}")
    except Exception as e:
        print(f"  [FAIL]: {type(e).__name__}: {e}")


# ============================================
# 测试 4: 行业板块列表
# ============================================

def test_industry_board():
    print()
    print("=" * 60)
    print("  测试 4: 行业板块")
    print("=" * 60)

    # 申万行业板块
    base_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": "20",
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:90+t:2",   # 行业板块
        "fields": "f2,f3,f4,f12,f14,f20",
    }

    t0 = time.time()
    try:
        resp = requests.get(base_url, params=params, timeout=15)
        data = resp.json()
        total = data.get("data", {}).get("total", 0)
        items = data.get("data", {}).get("diff", [])

        if items:
            print(f"  [OK] 行业板块: {total} 个, {time.time() - t0:.2f}s")
            for item in items[:5]:
                code = item.get("f12", "")
                name = item.get("f14", "")
                change_pct = item.get("f3", "")
                print(f"       {code} {name}  涨跌{change_pct}%")
            print(f"       ... (共 {total} 个)")
        else:
            print(f"  [FAIL]")
    except Exception as e:
        print(f"  [FAIL]: {type(e).__name__}: {e}")


# ============================================
# 测试 5: 行业板块日线
# ============================================

def test_industry_kline():
    print()
    print("=" * 60)
    print("  测试 5: 行业板块日线")
    print("=" * 60)

    test_boards = {
        "90.BK0489": "半导体",
        "90.BK0476": "银行",
        "90.BK0465": "白酒",
    }

    base_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    for secid, name in test_boards.items():
        t0 = time.time()
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "beg": "20250101",
            "end": datetime.now().strftime("%Y%m%d"),
        }
        try:
            resp = requests.get(base_url, params=params, timeout=15)
            data = resp.json()
            rc = data.get("rc")
            if rc != 0:
                print(f"  [FAIL] {name} ({secid}): rc={rc}")
                continue
            klines = data.get("data", {}).get("klines", [])
            if klines:
                last = klines[-1].split(",")
                print(f"  [OK] {name}: {len(klines)} rows, "
                      f"latest {last[0]} close={last[2]}, "
                      f"{time.time() - t0:.2f}s")
            else:
                print(f"  [FAIL] {name}: empty")
        except Exception as e:
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")


# ============================================
# 测试 6: 周线 / 月线
# ============================================

def test_periods():
    print()
    print("=" * 60)
    print("  测试 6: 多周期 (日/周/月线)")
    print("=" * 60)

    periods = {
        "101": "日线",
        "102": "周线",
        "103": "月线",
    }

    base_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    for klt, label in periods.items():
        t0 = time.time()
        params = {
            "secid": "1.600519",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": klt,
            "fqt": "1",
            "beg": "20200101",
            "end": datetime.now().strftime("%Y%m%d"),
        }
        try:
            resp = requests.get(base_url, params=params, timeout=15)
            data = resp.json()
            klines = data.get("data", {}).get("klines", [])
            if klines:
                last = klines[-1].split(",")
                print(f"  [OK] {label} (600519): {len(klines)} rows, "
                      f"latest {last[0]} close={last[2]}, "
                      f"{time.time() - t0:.2f}s")
            else:
                print(f"  [FAIL] {label}: empty")
        except Exception as e:
            print(f"  [FAIL] {label}: {type(e).__name__}: {e}")


# ============================================
# main
# ============================================

if __name__ == "__main__":
    t_start = time.time()
    print("东方财富 HTTP 接口连通性测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    test_kline()
    test_index()
    test_stock_list()
    test_industry_board()
    test_industry_kline()
    test_periods()

    print()
    print("=" * 60)
    print(f"  全部测试完成，总耗时 {time.time() - t_start:.1f}s")
    print("=" * 60)
