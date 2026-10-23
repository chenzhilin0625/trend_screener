"""
趋势强度指标：均线排列评分、ADX、均线斜率、综合评分
所有函数均为无副作用的纯计算，输入 DataFrame，输出数值。
"""

import numpy as np
import pandas as pd


def ma_alignment_score(df, ma_periods, window=60):
    """均线多头排列得分。

    计算最近 `window` 个交易日内，均线呈多头排列（短>中>长）
    的天数占比，并映射到 [-1, 1]。

    参数:
        df: DataFrame with 'close' column, index 为日期
        ma_periods: list[int]，如 [20, 60, 120]
        window: 统计窗口天数

    返回:
        float: -1.0（完美空头） ~ +1.0（完美多头）
    """
    if len(df) < max(ma_periods) + window:
        return 0.0

    close = df["close"]
    mas = {}
    for p in ma_periods:
        mas[p] = close.rolling(p).mean()

    bullish_days = 0
    bearish_days = 0
    valid_days = 0

    for i in range(-window, 0):
        vals = {}
        for p in ma_periods:
            v = mas[p].iloc[i]
            vals[p] = v

        if any(pd.isna(v) for v in vals.values()):
            continue

        sorted_vals = sorted(vals.items(), key=lambda x: x[1], reverse=True)
        sorted_periods = [x[0] for x in sorted_vals]

        valid_days += 1
        if sorted_periods == sorted(ma_periods):
            # 短周期值 > 长周期值 → 多头排列
            bullish_days += 1
        elif sorted_periods == sorted(ma_periods, reverse=True):
            bearish_days += 1

    if valid_days == 0:
        return 0.0

    return (bullish_days - bearish_days) / valid_days


def adx(df, period=20):
    """计算 ADX 和 +DI / -DI。

    基于 Wilder 原始算法。

    参数:
        df: DataFrame, columns=[high, low, close]
        period: ADX 计算周期

    返回:
        (adx, plus_di, minus_di) — 最近一天的值
    """
    if len(df) < period * 2:
        return 0.0, 0.0, 0.0

    high, low, close = df["high"], df["low"], df["close"]

    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()

    # Directional Movement
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)

    mask_plus = (up_move > 0) & (up_move > down_move)
    mask_minus = (down_move > 0) & (down_move > up_move)

    plus_dm[mask_plus] = up_move[mask_plus]
    minus_dm[mask_minus] = down_move[mask_minus]

    # Smoothed DM
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)

    # ADX
    di_sum = plus_di + minus_di
    di_sum = di_sum.replace(0, np.nan)
    dx = 100 * abs(plus_di - minus_di) / di_sum
    adx_val = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx_val.iloc[-1], plus_di.iloc[-1], minus_di.iloc[-1]


def ma_slope(df, period=20, slope_window=5):
    """计算均线斜率（最近 N 天的线性回归斜率，归一化）。

    参数:
        df: DataFrame with 'close'
        period: 均线周期
        slope_window: 取最近多少天的均线值做线性回归

    返回:
        float: 归一化斜率（正值=均线上升）
    """
    if len(df) < period + slope_window:
        return 0.0

    ma = df["close"].rolling(period).mean()
    recent = ma.dropna().iloc[-slope_window:]

    if len(recent) < slope_window:
        return 0.0

    x = np.arange(len(recent))
    slope = np.polyfit(x, recent.values, 1)[0]

    denom = recent.iloc[-1]
    if denom == 0 or pd.isna(denom):
        return 0.0
    return slope / denom


def detect_trend_emergence(df, adx_period=20, adx_threshold=20, lookback=5):
    """检测趋势初现信号。

    条件：
      1. ADX 最近 lookback 天内从 <adx_threshold 上穿到 >adx_threshold
      2. +DI > -DI（多头方向）
      3. 价格站上 MA(adx_period)

    返回:
        (emerged: bool, strength: float 0~1)
    """
    if len(df) < adx_period * 2 + lookback:
        return False, 0.0

    close = df["close"]
    adx_vals = []
    plus_vals = []
    minus_vals = []

    # 对最近 lookback+1 天逐个计算 ADX（从后往前推）
    for offset in range(lookback + 1):
        end = len(df) - offset
        sub = df.iloc[max(0, end - adx_period * 2):end]
        a, p, m = adx(sub, period=adx_period)
        adx_vals.append(a)
        plus_vals.append(p)
        minus_vals.append(m)

    adx_vals.reverse()
    plus_vals.reverse()
    minus_vals.reverse()

    # 检测上穿：之前 < threshold，现在 >= threshold
    if adx_vals[-1] < adx_threshold:
        return False, 0.0

    emerged = any(a < adx_threshold for a in adx_vals[:-1])
    if not emerged:
        return False, 0.0

    # 确认方向
    if plus_vals[-1] <= minus_vals[-1]:
        return False, 0.0

    # 价格站上均线
    ma = close.rolling(adx_period).mean().iloc[-1]
    if pd.isna(ma) or close.iloc[-1] <= ma:
        return False, 0.0

    # 强度：ADX 超过阈值的幅度
    strength = min((adx_vals[-1] - adx_threshold) / 20.0, 1.0)
    return True, round(strength, 2)


import pandas as pd


def detect_pullback(df, primary_up=True, minor_lookback=20):
    """检测长期上升趋势中的短期回调。

    条件：
      1. 长期趋势 up（由调用者传入 primary_up）
      2. 价格从 N 日高点回落超过 5%
      3. 但仍在 MA60 上方（长期趋势未破坏）
      4. 短期 ADX 下降或转负

    返回:
        (is_pullback: bool, depth: float, info: dict)
    """
    if not primary_up or len(df) < 60:
        return False, 0.0, {}

    close = df["close"]
    high_n = df["high"].rolling(minor_lookback).max().iloc[-1]
    current = close.iloc[-1]

    if pd.isna(high_n) or high_n <= 0:
        return False, 0.0, {}

    drawdown = (high_n - current) / high_n

    # 回调幅度 3% ~ 20%（太浅不算，太深可能转势）
    if drawdown < 0.03 or drawdown > 0.20:
        return False, drawdown, {}

    # 仍在 MA60 上方
    ma60 = close.rolling(60).mean().iloc[-1]
    if pd.isna(ma60) or current <= ma60:
        return False, drawdown, {}

    # 短期 ADX 减弱
    sub = df.iloc[-40:]
    a, p, m = adx(sub, period=7)  # 用 minor trend 的周期
    minor_weak = a < 18 or p < m  # ADX低或方向转空

    info = {
        "drawdown_pct": round(drawdown * 100, 1),
        "high_n": round(high_n, 2),
        "current": round(current, 2),
        "ma60": round(ma60, 2),
        "minor_weak": minor_weak,
    }

    return True, round(drawdown, 2), info


def trend_score_composite(df):
    """综合趋势强度评分（单一时间尺度，用于快速检查）。

    融合均线排列 + ADX 方向 + 近期动量。

    返回:
        float: -1.0 ~ 1.0
    """
    align = ma_alignment_score(df, [20, 60, 120])

    adx_val, plus_di, minus_di = adx(df, period=20)
    adx_dir = 1 if plus_di > minus_di else -1
    adx_norm = min(adx_val / 50.0, 1.0) * adx_dir

    slope_20 = ma_slope(df, 20, 10)
    slope_60 = ma_slope(df, 60, 10)
    slope_avg = (slope_20 + slope_60) / 2
    slope_norm = max(min(slope_avg * 200, 1.0), -1.0)

    composite = 0.5 * align + 0.3 * adx_norm + 0.2 * slope_norm
    return round(composite, 3)
