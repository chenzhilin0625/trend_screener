"""
布林带分析 —— 波动率收缩/扩张 + 突破方向预判

独立函数，输入 DataFrame，输出分析结果。
"""

import numpy as np
import pandas as pd


def bollinger_bands(df, period=20, nbdev=2.0):
    """计算布林带。

    返回:
        dict: {middle, upper, lower, width, width_pct, bb_position}
    """
    if len(df) < period:
        return None

    close = df["close"]
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()

    upper = middle + nbdev * std
    lower = middle - nbdev * std

    latest_mid = float(middle.iloc[-1])
    latest_up = float(upper.iloc[-1])
    latest_lo = float(lower.iloc[-1])
    latest_close = float(close.iloc[-1])

    # 带宽（相对宽度）
    width = (latest_up - latest_lo) / latest_mid if latest_mid > 0 else 0

    # 价格在布林带中的位置（0=下轨, 1=上轨）
    bb_range = latest_up - latest_lo
    position = (latest_close - latest_lo) / bb_range if bb_range > 0 else 0.5

    return {
        "middle": round(latest_mid, 2),
        "upper": round(latest_up, 2),
        "lower": round(latest_lo, 2),
        "width": round(width, 4),
        "width_pct": round(width * 100, 2),
        "position": round(position, 3),
        "close": round(latest_close, 2),
    }


def detect_squeeze(df, period=20, lookback=125, percentile=20):
    """检测布林带收缩（Squeeze）—— 波动率极低，预示即将大幅波动。

    Bollinger Band Squeeze 是 John Bollinger 提出的经典信号:
      当带宽收缩到近期最低水平时，预示即将出现大幅方向性波动。

    返回:
        (is_squeeze: bool, info: dict)
    """
    if len(df) < lookback:
        return False, {"reason": "数据不足"}

    close = df["close"]
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + 2 * std
    lower = middle - 2 * std

    # 计算历史带宽
    widths = ((upper - lower) / middle).dropna()

    if len(widths) < lookback:
        return False, {"reason": "数据不足"}

    current_width = float(widths.iloc[-1])
    threshold = np.percentile(widths.iloc[-lookback:], percentile)

    # 收缩判定
    is_squeeze = current_width < threshold

    # 方向预判：结合价格在带中的位置
    bb = bollinger_bands(df, period=period)
    position = bb["position"] if bb else 0.5

    if position > 0.6:
        bias = "看涨（价格偏上轨）"
    elif position < 0.4:
        bias = "看跌（价格偏下轨）"
    else:
        bias = "方向不明（价格在中轨附近）"

    return is_squeeze, {
        "current_width_pct": round(current_width * 100, 2),
        "percentile_threshold": round(threshold * 100, 2),
        "position": round(position, 3),
        "bias": bias,
    }


def detect_expansion(df, period=20, lookback=60, multiplier=1.5):
    """检测布林带扩张 —— 波动率突然放大，确认趋势启动。

    突破后的布林带扩张是真突破的重要确认信号。

    返回:
        (is_expanding: bool, info: dict)
    """
    if len(df) < lookback + period:
        return False, {"reason": "数据不足"}

    close = df["close"]
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + 2 * std
    lower = middle - 2 * std

    widths = ((upper - lower) / middle).dropna()
    if len(widths) < 10:
        return False, {"reason": "数据不足"}

    recent = widths.iloc[-5:].mean()
    prev = widths.iloc[-15:-5].mean()

    is_expanding = recent > prev * multiplier

    return is_expanding, {
        "recent_width": round(recent * 100, 2),
        "prev_width": round(prev * 100, 2),
        "expansion_ratio": round(recent / prev, 2) if prev > 0 else 0,
    }


def bollinger_signal(df):
    """布林带综合信号。

    返回:
        dict: {squeeze, expansion, bands, signal}
        signal: "收缩-待突破" / "扩张-趋势确认" / "正常"
    """
    bb = bollinger_bands(df)
    sq, sq_info = detect_squeeze(df)
    ex, ex_info = detect_expansion(df)

    if sq:
        signal = f"收缩-待突破 ({sq_info['bias']})"
    elif ex:
        signal = "扩张-趋势确认"
    else:
        signal = "正常"

    return {
        "bands": bb,
        "is_squeeze": sq,
        "squeeze_info": sq_info,
        "is_expansion": ex,
        "expansion_info": ex_info,
        "signal": signal,
    }
