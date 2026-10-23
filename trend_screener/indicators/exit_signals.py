"""
退出/止损信号 —— 吊灯止损、ATR移动止损、移动止盈

所有函数独立，输入 DataFrame + 仓位信息，输出止损/止盈价格。
"""

import numpy as np
import pandas as pd
from indicators.trend_quality import atr


# ================================================================
#  吊灯止损（Chandelier Exit）
# ================================================================

def chandelier_exit(df, atr_multiple=3.0, atr_period=22):
    """吊灯止损：从最高点回撤 N×ATR 时退出。

    公式:
      多头止损 = N日最高价 - N×ATR

    这是最经典的趋势跟踪止损方法之一（LeBeau）。

    返回:
        (stop_price: float, info: dict)
    """
    if len(df) < atr_period:
        return None, {"reason": "数据不足"}

    high = df["high"]
    atr_val = atr(df, period=atr_period)

    if atr_val == 0:
        return None, {"reason": "ATR=0"}

    highest = high.iloc[-atr_period:].max()
    stop = highest - atr_multiple * atr_val

    return round(stop, 2), {
        "highest_n": round(highest, 2),
        "atr": round(atr_val, 2),
        "stop": round(stop, 2),
        "current": round(df["close"].iloc[-1], 2),
        "stop_pct": round((stop / df["close"].iloc[-1] - 1) * 100, 1) if df["close"].iloc[-1] > 0 else 0,
    }


# ================================================================
#  ATR 移动止损（Trailing Stop）
# ================================================================

def atr_trailing_stop(df, atr_multiple=2.0, atr_period=20):
    """ATR 移动止损：随价格上涨自动上移止损线。

    逻辑:
      止损线 = close - N×ATR，只上移不下移

    返回:
        (stop_price: float, info: dict)
    """
    if len(df) < atr_period:
        return None, {"reason": "数据不足"}

    atr_val = atr(df, period=atr_period)
    close = df["close"]

    if atr_val == 0:
        return None, {"reason": "ATR=0"}

    # 简单版：当前价 - N×ATR
    stop = close.iloc[-1] - atr_multiple * atr_val

    # 更精确版：回溯从头计算动态止损（只上移）
    trailing_stops = []
    for i in range(atr_period, len(df)):
        sub = df.iloc[:i + 1]
        a = atr(sub, period=atr_period)
        c = sub["close"].iloc[-1]
        s = c - atr_multiple * a
        if trailing_stops:
            s = max(s, trailing_stops[-1])  # 只上移
        trailing_stops.append(s)

    dynamic_stop = round(trailing_stops[-1], 2) if trailing_stops else stop
    stop_pct = round((dynamic_stop / close.iloc[-1] - 1) * 100, 1) if close.iloc[-1] > 0 else 0

    return dynamic_stop, {
        "atr": round(atr_val, 2),
        "simple_stop": round(stop, 2),
        "trailing_stop": dynamic_stop,
        "current": round(close.iloc[-1], 2),
        "stop_pct": stop_pct,
    }


# ================================================================
#  移动止盈（基于 MA）
# ================================================================

def ma_trailing_stop(df, ma_period=20, close_below_days=2):
    """均线移动止盈：价格连续 N 天收盘在 MA 下方时止盈。

    简单但有效，适合趋势跟踪策略。

    返回:
        (should_exit: bool, exit_price: float, info: dict)
    """
    if len(df) < ma_period + close_below_days:
        return False, 0, {"reason": "数据不足"}

    close = df["close"]
    ma = close.rolling(ma_period).mean()

    below_count = sum(
        1 for i in range(close_below_days)
        if close.iloc[-(i + 1)] < ma.iloc[-(i + 1)]
        if pd.notna(ma.iloc[-(i + 1)])
    )

    should_exit = below_count >= close_below_days

    return should_exit, round(close.iloc[-1], 2), {
        "ma": round(ma.iloc[-1], 2),
        "below_days": below_count,
        "required": close_below_days,
    }


# ================================================================
#  综合退出判断
# ================================================================

def evaluate_exit(df, entry_price=None):
    """综合退出信号：综合多种退出方法。

    返回:
        dict: {
            "should_exit": bool,
            "reasons": list[str],
            "chandelier": ...,
            "atr_trail": ...,
            "ma_trail": ...,
        }
    """
    reasons = []
    result = {
        "should_exit": False,
        "reasons": reasons,
        "current": round(df["close"].iloc[-1], 2),
    }

    # 1. 吊灯止损
    ch_stop, ch_info = chandelier_exit(df)
    result["chandelier"] = ch_info
    if ch_stop and df["close"].iloc[-1] < ch_stop:
        reasons.append(f"吊灯止损触发({ch_stop})")
        result["should_exit"] = True

    # 2. ATR 移动止损
    atr_stop, atr_info = atr_trailing_stop(df)
    result["atr_trail"] = atr_info
    if atr_stop and df["close"].iloc[-1] < atr_stop:
        reasons.append(f"ATR移动止损触发({atr_stop})")
        result["should_exit"] = True

    # 3. 均线止盈
    should, exit_p, ma_info = ma_trailing_stop(df)
    result["ma_trail"] = ma_info
    if should:
        reasons.append(f"均线止盈(跌破MA{20})")
        result["should_exit"] = True

    # 4. 如果设定了入场价，计算盈亏
    if entry_price:
        pnl_pct = round((df["close"].iloc[-1] / entry_price - 1) * 100, 1)
        result["pnl_pct"] = pnl_pct

    return result
