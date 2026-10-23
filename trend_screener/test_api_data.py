"""
股票数据接口连通性测试

分别测试 baostock / akshare 的可用性、响应速度、数据完整性。
不依赖本地 TDX 文件，纯网络调用。

用法:
    python test_api_data.py                 # 全部测试
    python test_api_data.py --quick         # 快速冒烟（每源 1 只）
    python test_api_data.py --source bs     # 仅测 baostock
    python test_api_data.py --source ak     # 仅测 akshare
"""

import os
import sys
import time
import traceback
from datetime import datetime

# 关掉代理 —— akshare 经常因为系统代理配置而连不上
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ["NO_PROXY"] = "*"

# ------------------------------
# 工具函数（纯 ASCII）
# ------------------------------

def banner(title):
    w = 60
    print()
    print("=" * w)
    print(f"  {title}")
    print("=" * w)

def sub(msg, ok=True):
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {msg}")

def sub_value(key, value):
    print(f"       {key}: {value}")

def elapsed(t0):
    return f"{time.time() - t0:.2f}s"


# ------------------------------
# baostock
# ------------------------------

TEST_STOCKS_BS = {
    "sh.600519": "贵州茅台",
    "sh.601318": "中国平安",
    "sz.000001": "平安银行",
    "sz.300750": "宁德时代",
    "sh.688981": "中芯国际",
}


def test_baostock(quick=False):
    import baostock as bs

    stocks_to_test = dict(list(TEST_STOCKS_BS.items())[:1]) if quick else TEST_STOCKS_BS

    banner("Baostock 接口测试")
    t0 = time.time()

    sub("导入 baostock 成功")

    # ---- 登录 ----
    t_login = time.time()
    lg = bs.login()
    if lg.error_code == "0":
        sub(f"登录成功 ({lg.error_msg})", True)
        sub_value("耗时", elapsed(t_login))
    else:
        sub(f"登录失败: {lg.error_msg}", False)
        print("  [终止] baostock 登录失败，跳过后续测试")
        return

    # ---- 股票列表 ----
    t_list = time.time()
    rs = bs.query_stock_basic()
    if rs.error_code != "0":
        sub(f"获取股票列表失败: {rs.error_msg}", False)
    else:
        count = 0
        sample_codes = []
        while rs.next() and count < 20000:
            row = rs.get_row_data()
            if row[2] == "1":
                sample_codes.append(row[0])
            count += 1
        sub(f"获取股票列表成功", True)
        sub_value("全市场数量", f"{count} 只")
        sub_value("正常上市", f"{len(sample_codes)} 只")
        sub_value("耗时", elapsed(t_list))
        if sample_codes:
            sub_value("示例", f"{sample_codes[0]}, {sample_codes[1]}, {sample_codes[2]} ...")

    # ---- 日线 K 线 ----
    end_date = datetime.now().strftime("%Y-%m-%d")
    print(f"\n  --- 日线数据下载 (日期范围: 2025-01-01 ~ {end_date}) ---")

    ok_count = 0
    fail_count = 0
    for code_full, name in stocks_to_test.items():
        t_one = time.time()
        try:
            rs = bs.query_history_k_data_plus(
                code_full,
                "date,open,high,low,close,volume,amount",
                start_date="2025-01-01",
                end_date=end_date,
                frequency="d",
                adjustflag="2",
            )
            if rs.error_code != "0":
                sub(f"{code_full} ({name}) 查询失败: {rs.error_msg}", False)
                fail_count += 1
                continue

            rows = []
            while rs.next():
                row = rs.get_row_data()
                if row[1] == "" or row[1] == "0.000000":
                    continue
                rows.append(row)

            if rows:
                first_row = rows[0]
                last_row = rows[-1]
                sub(f"{code_full} ({name}) 成功", True)
                sub_value("记录数", f"{len(rows)} 行")
                sub_value("日期范围", f"{first_row[0]} ~ {last_row[0]}")
                sub_value("最新收盘", f"{last_row[4]}")
                sub_value("耗时", elapsed(t_one))
                ok_count += 1
            else:
                sub(f"{code_full} ({name}) 无数据", False)
                fail_count += 1
        except Exception as e:
            sub(f"{code_full} ({name}) 异常: {type(e).__name__}: {e}", False)
            fail_count += 1

    # ---- 指数 ----
    print()
    indices = {"sh.000300": "沪深300", "sh.000001": "上证指数"}
    for code_full, name in indices.items():
        t_one = time.time()
        try:
            rs = bs.query_history_k_data_plus(
                code_full,
                "date,open,high,low,close,volume,amount",
                start_date="2025-01-01",
                end_date=end_date,
                frequency="d",
                adjustflag="2",
            )
            if rs.error_code == "0":
                count = 0
                last_close = ""
                while rs.next():
                    row = rs.get_row_data()
                    if row[4] and row[4] != "0.000000":
                        count += 1
                        last_close = row[4]
                sub(f"{name} ({code_full}) 成功", True)
                sub_value("记录数", f"{count} 行")
                sub_value("最新", last_close)
                sub_value("耗时", elapsed(t_one))
            else:
                sub(f"{name} ({code_full}) 失败: {rs.error_msg}", False)
        except Exception as e:
            sub(f"{name} ({code_full}) 异常: {type(e).__name__}: {e}", False)

    # ---- 登出 ----
    bs.logout()
    sub("登出成功")

    # 总结
    print()
    total_elapsed = elapsed(t0)
    tested = ok_count + fail_count
    print(f"  Baostock 测试完成: {ok_count}/{tested} 成功, 总耗时 {total_elapsed}")


# ------------------------------
# akshare
# ------------------------------

TEST_STOCKS_AK = {
    "600519": "贵州茅台",
    "601318": "中国平安",
    "000001": "平安银行",
    "300750": "宁德时代",
    "688981": "中芯国际",
}


def test_akshare(quick=False):
    import akshare as ak
    import pandas as pd

    stocks_to_test = dict(list(TEST_STOCKS_AK.items())[:1]) if quick else TEST_STOCKS_AK

    banner("Akshare 接口测试")
    t0 = time.time()

    # ---- 导入 ----
    sub("导入 akshare 成功")
    try:
        ver = ak.__version__
        sub_value("版本", ver)
    except Exception:
        pass

    # ---- 股票列表 ----
    print()
    t_list = time.time()
    try:
        df = ak.stock_info_a_code_name()
        sub("stock_info_a_code_name() 成功", True)
        sub_value("数量", f"{len(df)} 只")
        sub_value("耗时", elapsed(t_list))
        sub_value("列名", ", ".join(df.columns.tolist()))
    except Exception as e:
        sub(f"stock_info_a_code_name() 失败: {type(e).__name__}: {e}", False)

    # ---- 日线 K 线 ---- stock_zh_a_hist ----
    print(f"\n  --- 日线数据下载 (stock_zh_a_hist, period='daily') ---")

    ok_count = 0
    fail_count = 0
    for code, name in stocks_to_test.items():
        t_one = time.time()
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date="20250101",
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq",
            )
            if df is not None and not df.empty:
                sub(f"{code} ({name}) 成功", True)
                sub_value("记录数", f"{len(df)} 行")
                sub_value("日期范围",
                          f"{df.iloc[0]['日期']} ~ {df.iloc[-1]['日期']}")
                sub_value("最新收盘", f"{df.iloc[-1]['收盘']}")
                sub_value("耗时", elapsed(t_one))
                ok_count += 1
            else:
                sub(f"{code} ({name}) 返回空数据", False)
                fail_count += 1
        except Exception as e:
            sub(f"{code} ({name}) 异常: {type(e).__name__}: {e}", False)
            fail_count += 1

    # ---- 备选接口: stock_zh_a_daily ----
    print(f"\n  --- 备选接口 (stock_zh_a_daily, adjust='qfq') ---")
    alt_ok = 0
    for code, name in stocks_to_test.items():
        t_one = time.time()
        try:
            prefix = "sh" if code.startswith(("6", "68")) else "sz"
            df = ak.stock_zh_a_daily(
                symbol=f"{prefix}{code}",
                adjust="qfq",
            )
            if df is not None and not df.empty:
                sub(f"{code} ({name}) stock_zh_a_daily 成功", True)
                sub_value("记录数", f"{len(df)} 行")
                sub_value("日期范围", f"{df.iloc[0]['date']} ~ {df.iloc[-1]['date']}")
                sub_value("耗时", elapsed(t_one))
                alt_ok += 1
            else:
                sub(f"{code} ({name}) stock_zh_a_daily 返回空", False)
        except Exception as e:
            sub(f"{code} ({name}) stock_zh_a_daily 异常: {type(e).__name__}", False)

    # ---- 指数 ----
    print(f"\n  --- 指数数据 ---")
    try:
        df = ak.stock_zh_index_daily(symbol="sh000300")
        if df is not None and not df.empty:
            sub("沪深300 (sh000300) 成功", True)
            sub_value("记录数", f"{len(df)} 行")
            sub_value("最新日期", f"{df.iloc[-1]['date']}")
            sub_value("最新收盘", f"{df.iloc[-1]['close']}")
        else:
            sub("沪深300 返回空", False)
    except Exception as e:
        sub(f"沪深300 异常: {type(e).__name__}: {e}", False)

    try:
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is not None and not df.empty:
            sub("上证指数 (sh000001) 成功", True)
            sub_value("记录数", f"{len(df)} 行")
    except Exception as e:
        sub(f"上证指数 异常: {type(e).__name__}", False)

    # ---- 行业板块 ----
    print(f"\n  --- 行业板块 (stock_board_industry_summary_ths) ---")
    try:
        df = ak.stock_board_industry_summary_ths()
        if df is not None and not df.empty:
            sub("行业板块列表成功", True)
            sub_value("数量", f"{len(df)} 个")
            sub_value("列名", ", ".join(df.columns.tolist()[:5]) + " ...")
        else:
            sub("行业板块列表返回空", False)
    except Exception as e:
        sub(f"行业板块异常: {type(e).__name__}: {e}", False)

    # 总结
    total_elapsed = elapsed(t0)
    total_tested = ok_count + fail_count
    print()
    print(f"  Akshare 测试完成: {ok_count}/{total_tested} 成功(主接口), "
          f"备选 {alt_ok}/{len(stocks_to_test)} 成功, 总耗时 {total_elapsed}")


# ------------------------------
# 交叉验证
# ------------------------------

def cross_validate():
    """同一只股票，baostock vs akshare 数据对比。"""
    import baostock as bs
    import akshare as ak

    banner("交叉验证: baostock vs akshare (600519 贵州茅台)")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = "2026-01-01"

    # --- baostock ---
    bs.login()
    rs = bs.query_history_k_data_plus(
        "sh.600519",
        "date,open,high,low,close,volume,amount",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="2",
    )
    bs_data = {}
    while rs.next():
        row = rs.get_row_data()
        if row[1] and row[1] != "0.000000":
            bs_data[row[0]] = {
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
            }
    bs.logout()

    # --- akshare ---
    try:
        df_ak = ak.stock_zh_a_hist(
            symbol="600519",
            period="daily",
            start_date="20260101",
            end_date=end_date.replace("-", ""),
            adjust="qfq",
        )
        ak_data = {}
        if df_ak is not None and not df_ak.empty:
            for _, row in df_ak.iterrows():
                d = str(row["日期"]).replace("-", "")
                ak_data[d] = {
                    "open": float(row["开盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "close": float(row["收盘"]),
                }
    except Exception as e:
        sub(f"Akshare 获取失败: {type(e).__name__}: {e}", False)
        return

    # --- 对比 ---
    sub("Baostock 记录数", str(len(bs_data)))
    sub("Akshare 记录数", str(len(ak_data)))

    common_dates = sorted(set(bs_data) & set(ak_data))
    sub("共同日期数", str(len(common_dates)))

    if not common_dates:
        sub("无共同日期，无法对比", False)
        return

    diffs = 0
    max_diff = 0.0
    for d in common_dates[:20]:
        diff = abs(bs_data[d]["close"] - ak_data[d]["close"])
        if diff > 0.01:
            diffs += 1
        if diff > max_diff:
            max_diff = diff

    sub("收盘价最大偏差", f"{max_diff:.4f}")
    sub(f"偏差 > 0.01 的天数", f"{diffs}/{min(20, len(common_dates))}")

    if max_diff < 0.05 and diffs < 2:
        sub("结论: 两源数据高度一致 OK", True)
    else:
        sub("结论: 存在显著偏差，请核实", False)

    # 展示最近 5 天对比
    print(f"\n  {'日期':<12} {'bs收盘':>10} {'ak收盘':>10} {'偏差':>10}")
    print(f"  {'-'*44}")
    for d in common_dates[-5:]:
        bs_close = bs_data[d]["close"]
        ak_close = ak_data[d]["close"]
        delta = bs_close - ak_close
        print(f"  {d:<12} {bs_close:>10.2f} {ak_close:>10.2f} {delta:>10.4f}")


# ------------------------------
# main
# ------------------------------

if __name__ == "__main__":
    quick = "--quick" in sys.argv
    source_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith("--source="):
            source_filter = arg.split("=", 1)[1].lower()

    t_start = time.time()

    print("股票数据接口连通性测试")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    mode_desc = "快速" if quick else "完整"
    source_desc = source_filter or "全"
    print(f"模式: {mode_desc}, 数据源: {source_desc}")

    try:
        if source_filter is None or source_filter in ("bs", "baostock"):
            test_baostock(quick=quick)
    except ImportError:
        sub("baostock 未安装", False)
    except Exception as e:
        print(f"  Baostock 测试异常: {e}")
        traceback.print_exc()

    try:
        if source_filter is None or source_filter in ("ak", "akshare"):
            test_akshare(quick=quick)
    except ImportError:
        sub("akshare 未安装", False)
    except Exception as e:
        print(f"  Akshare 测试异常: {e}")
        traceback.print_exc()

    try:
        if source_filter is None:
            cross_validate()
    except Exception as e:
        print(f"  交叉验证异常: {e}")
        traceback.print_exc()

    print()
    print("=" * 60)
    total = elapsed(t_start)
    print(f"  全部测试完成，总耗时 {total}")
    print("=" * 60)
