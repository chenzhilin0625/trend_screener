"""
相对强度（RS）计算 —— 横截面排名法

核心逻辑：一个行业/个股的"强度"不是其绝对涨跌幅，而是
它在所有同类中排第几。
"""

import pandas as pd
import numpy as np


def calc_rs_rank(all_returns, periods=None):
    """计算横截面 RS 排名。

    适用场景：多个行业板块映射到同一个 RS 排名体系。

    参数:
        all_returns: dict {code: Series(index=date, values=日收益率)}
        periods: list[int]，要计算的周期，如 [20, 40, 60]

    返回:
        dict: {code: float}，每个标的的 RS 得分 (0~1)
              RS 越高 = 在所有标的中越强
    """
    if periods is None:
        periods = [20, 40, 60]

    if not all_returns:
        return {}

    codes = list(all_returns.keys())
    rs_scores = {code: [] for code in codes}

    for p in periods:
        # 计算所有标的在过去 p 日的累计收益
        period_rets = {}
        for code, rets in all_returns.items():
            if len(rets) < p:
                continue
            period_rets[code] = rets.iloc[-p:].sum()

        if len(period_rets) < 2:
            continue

        # 计算横截面排名百分位
        ret_series = pd.Series(period_rets)
        ranks = ret_series.rank(pct=True)

        for code in codes:
            if code in ranks.index:
                rs_scores[code].append(ranks[code])

    # 取各周期的均值
    result = {}
    for code, scores in rs_scores.items():
        if scores:
            result[code] = round(float(np.mean(scores)), 3)
        else:
            result[code] = 0.0

    return result


def calc_rs_vs_benchmark(target_returns, benchmark_returns, periods=None):
    """计算单个标的相对基准的 RS。

    参数:
        target_returns: Series，标的日收益率
        benchmark_returns: Series，基准日收益率
        periods: list[int]

    返回:
        float: RS 值。>1.0 表示跑赢基准，<1.0 表示跑输。
    """
    if periods is None:
        periods = [20, 40, 60]

    if target_returns is None or benchmark_returns is None:
        return 1.0

    values = []
    for p in periods:
        if len(target_returns) < p or len(benchmark_returns) < p:
            continue
        target_ret = target_returns.iloc[-p:].sum()
        bench_ret = benchmark_returns.iloc[-p:].sum()
        if bench_ret == 0 or pd.isna(bench_ret):
            continue
        values.append(target_ret / bench_ret)

    return round(float(np.mean(values)), 3) if values else 1.0


def stock_relative_strength(stock_df, index_df, industry_df, period=20):
    """个股相对于大盘和行业的双重 RS。

    返回:
        (rs_vs_index: float, rs_vs_industry: float)
    """
    try:
        stock_close = stock_df["close"]
        index_close = index_df["close"]
        ind_close = industry_df["close"]
    except (KeyError, AttributeError):
        return 1.0, 1.0

    if (len(stock_close) < period or len(index_close) < period
            or len(ind_close) < period):
        return 1.0, 1.0

    stock_ret = stock_close.iloc[-1] / stock_close.iloc[-period] - 1
    index_ret = index_close.iloc[-1] / index_close.iloc[-period] - 1
    ind_ret = ind_close.iloc[-1] / ind_close.iloc[-period] - 1

    rs_index = stock_ret / index_ret if index_ret != 0 else 1.0
    rs_ind = stock_ret / ind_ret if ind_ret != 0 else 1.0

    return round(rs_index, 3), round(rs_ind, 3)
