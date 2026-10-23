"""
量价配合分析 —— 上涨放量 / 下跌缩量 = 趋势健康。
"""

import pandas as pd
def check_volume_healthy(df, window=20):
    """检查量价配合是否健康。

    趋势健康的特征：
      - 上涨日平均成交量 > 下跌日平均成交量
      - 量比 > 1.1 表示有需求支撑

    参数:
        df: DataFrame, columns=[close, volume]
        window: 统计窗口天数

    返回:
        bool: True = 量价健康
    """
    if len(df) < window:
        return False

    recent = df.tail(window).copy()
    recent["ret"] = recent["close"].pct_change()

    up_mask = recent["ret"] > 0
    down_mask = recent["ret"] < 0

    up_vol = recent.loc[up_mask, "volume"].mean()
    down_vol = recent.loc[down_mask, "volume"].mean()

    if pd.isna(up_vol) or pd.isna(down_vol) or down_vol == 0:
        return False
    return up_vol / down_vol > 1.1


def volume_ratio(df, window=20):
    """计算近期量比（当前成交量 / N日均量）。

    返回:
        float: >1 表示放量，<1 表示缩量
    """
    if len(df) < window:
        return 1.0

    vol = df["volume"]
    current = vol.iloc[-1]
    avg = vol.iloc[-window:].mean()

    if avg == 0 or pd.isna(avg):
        return 1.0
    return round(current / avg, 2)


def volume_trend_score(df):
    """价格趋势中的量能确认评分。

    返回:
        float: 0~1，越高越确认
    """
    if len(df) < 20:
        return 0.5

    df = df.tail(20).copy()
    df["ret"] = df["close"].pct_change()
    df["vol_chg"] = df["volume"].pct_change()

    # 价格上涨且成交量也上涨的天数占比
    confirm_days = ((df["ret"] > 0) & (df["vol_chg"] > df["vol_chg"].median())).sum()
    up_days = (df["ret"] > 0).sum()

    if up_days == 0:
        return 0.0

    return round(confirm_days / up_days, 2)
