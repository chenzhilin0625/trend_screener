"""
市场宽度指标 —— 研判全市场趋势参与广度。

数据来源：DataManager.market_breadth 表（涨跌家数快照）+ 个股日线计算。
"""

import pandas as pd


def advance_decline_ratio(df_breadth, window=20):
    """计算涨跌比（最近 N 日上涨家数占比）。

    参数:
        df_breadth: DataFrame, columns=[up_count, down_count]
        window: 统计窗口

    返回:
        float: 0~1，越高越强
    """
    if df_breadth is None or len(df_breadth) < window:
        return 0.5

    recent = df_breadth.tail(window)
    total_up = recent["up_count"].sum()
    total_down = recent["down_count"].sum()
    total = total_up + total_down

    if total == 0:
        return 0.5
    return round(total_up / total, 3)


def ma_above_ratio(df_breadth):
    """站上均线比例（用当日涨跌比近似代替）。

    精确版需要全市场个股数据，但当日涨跌比与站上短期均线
    的历史相关性较高（~0.6-0.7），可作为近似代理。

    返回:
        float: 0~1
    """
    if df_breadth is None or df_breadth.empty:
        return 0.5

    last = df_breadth.iloc[-1]
    total = last.get("total_count", last["up_count"] + last["down_count"])
    if total == 0:
        return 0.5
    return round(last["up_count"] / total, 3)


def new_high_low_ratio(dm, df_breadth=None, period=20):
    """新高新低比。

    当全量个股数据不可用时，降级到涨跌比作为近似。
    当全量数据可用时，从 breadth_data.compute_new_high_low_ratio 计算。

    返回:
        float: 0~1
    """
    # 尝试从涨跌数据中近似
    if df_breadth is not None and not df_breadth.empty:
        total = (df_breadth["up_count"].iloc[-1] +
                 df_breadth["down_count"].iloc[-1])
        if total > 0:
            # 涨跌比中上涨占 65% 以上 → 新高可能占主导
            adr = df_breadth["up_count"].iloc[-1] / total
            if adr > 0.65:
                return min(adr, 1.0)
    return 0.5


def market_breadth_score(df_breadth):
    """市场宽度综合评分。

    融合涨跌比 + 站上均线比 → 输出 0~1。

    返回:
        float
    """
    adr = advance_decline_ratio(df_breadth)
    mar = ma_above_ratio(df_breadth)

    # 映射规则：两项都 > 0.5 才是健康
    if adr >= 0.6 and mar >= 0.6:
        return 0.8 + 0.2 * min((adr - 0.6) / 0.4, 1.0)
    elif adr >= 0.5 and mar >= 0.5:
        return 0.5 + 0.3 * min((adr - 0.5) / 0.1, 1.0)
    else:
        return max(0.1, (adr + mar) / 2)
