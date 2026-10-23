"""
趋势质量判断 —— 震荡过滤、假突破、见顶检测、加速检测、回调vs反转

所有函数独立、无副作用，输入 DataFrame，输出 dict/bool。
"""

import numpy as np
import pandas as pd
from indicators.trend_strength import adx as calc_adx, ma_slope


# ================================================================
#  P0: 震荡过滤器 —— 绝对不交易规则
# ================================================================

def is_ranging(df, adx_period=20, adx_threshold=20, consecutive_days=3):
    """检查市场是否处于震荡/无趋势状态。

    震荡判定:
      1. ADX < adx_threshold 且持续 consecutive_days 天
      2. +DI 和 -DI 反复交叉（方向不明确）

    返回:
        (is_ranging: bool, info: dict)
    """
    if len(df) < adx_period * 2 + consecutive_days:
        return False, {"reason": "数据不足"}

    close = df["close"]
    adx_vals = []
    di_cross_count = 0

    for offset in range(consecutive_days + 3):
        end = len(df) - offset
        sub = df.iloc[max(0, end - adx_period * 2):end]
        a, p, m = calc_adx(sub, period=adx_period)
        adx_vals.append(a)
        if offset > 0:
            prev_a, prev_p, prev_m = calc_adx(
                df.iloc[max(0, end - 1 - adx_period * 2):end - 1], period=adx_period
            )
            if (prev_p > prev_m) != (p > m):
                di_cross_count += 1

    # 最近 N 天 ADX 都低于阈值
    recent_adx = adx_vals[:consecutive_days]
    all_below = all(a < adx_threshold for a in recent_adx)

    # DI 频繁交叉说明方向不明
    direction_unclear = di_cross_count >= 2

    is_ranging = all_below and direction_unclear

    return is_ranging, {
        "adx_latest": round(adx_vals[0], 1),
        "adx_min_recent": round(min(recent_adx), 1),
        "di_crosses": di_cross_count,
        "all_below_threshold": all_below,
    }


# ================================================================
#  P0: 假突破过滤器
# ================================================================

def validate_breakout(df, breakout_direction="up", volume_ratio=1.5, close_days=2):
    """验证突破是否有效。

    真突破三要素:
      1. 价格突破关键位（由调用者判断）
      2. 成交量 > N日均量 × volume_ratio
      3. 连续 close_days 天收盘站稳突破位上方

    返回:
        (is_valid: bool, info: dict)
    """
    if len(df) < 30:
        return False, {"reason": "数据不足"}

    close = df["close"]
    volume = df["volume"]

    avg_vol = volume.iloc[-20:].mean()
    latest_vol = volume.iloc[-1]

    vol_ok = latest_vol > avg_vol * volume_ratio if avg_vol > 0 else False

    # 连续 close_days 收盘在 MA20 上方（简化版突破确认）
    ma20 = close.rolling(20).mean()
    close_above = [close.iloc[-(i + 1)] > ma20.iloc[-(i + 1)] if pd.notna(ma20.iloc[-(i + 1)]) else False
                   for i in range(close_days)]
    consecutive_ok = all(close_above)

    is_valid = vol_ok and consecutive_ok

    return is_valid, {
        "volume_ratio": round(latest_vol / avg_vol, 2) if avg_vol > 0 else 0,
        "volume_ok": vol_ok,
        "consecutive_ok": consecutive_ok,
        "ma20": round(ma20.iloc[-1], 2) if pd.notna(ma20.iloc[-1]) else 0,
        "close": round(close.iloc[-1], 2),
    }


# ================================================================
#  P1: 见顶检测 —— 多维综合
# ================================================================

def detect_top_exhaustion(df, lookback=60):
    """检测趋势见顶信号（多维综合）。

    检测项:
      1. 量价背离: 价格创新高但量萎缩 >20%
      2. ADX 衰竭: ADX 从 >35 高位回落
      3. 放量滞涨: 近5日在高位窄幅震荡 + 放量
      4. HL 失败: 跌破前一显著低点

    返回:
        (exhaustion_level: int 0~3, signals: list[str], info: dict)
        exhaustion_level: 0=无信号, 1=弱警告, 2=中等警告, 3=强警告
    """
    if len(df) < lookback:
        return 0, [], {"reason": "数据不足"}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    signals = []
    score = 0

    # --- 1. 量价背离 ---
    recent = df.iloc[-60:].copy()
    recent["hh_60"] = recent["high"].rolling(20).max()
    peak_mask = recent["high"] == recent["hh_60"]
    peak_indices = recent.index[peak_mask]

    if len(peak_indices) >= 2:
        last_peak = peak_indices[-1]
        prev_peak = peak_indices[-2]
        last_vol = volume.loc[last_peak:].mean()
        prev_vol = volume.loc[prev_peak:last_peak].mean()

        if pd.notna(last_vol) and pd.notna(prev_vol) and prev_vol > 0:
            vol_decline = 1 - last_vol / prev_vol
            price_rise = (high.loc[last_peak] / high.loc[prev_peak] - 1) if high.loc[prev_peak] > 0 else 0

            if vol_decline > 0.20 and price_rise > 0:
                signals.append(f"量价背离(量缩{vol_decline:.0%})")
                score += 1

    # --- 2. ADX 衰竭 ---
    adx_now, p_now, m_now = calc_adx(df.iloc[-40:], period=14)
    adx_prev, _, _ = calc_adx(df.iloc[-60:-20], period=14)

    if adx_prev > 35 and adx_now < adx_prev - 8:
        signals.append(f"ADX衰竭({adx_prev:.0f}→{adx_now:.0f})")
        score += 1

    # --- 3. 放量滞涨 ---
    if len(close) >= 5:
        recent_5 = close.iloc[-5:]
        range_pct = (recent_5.max() - recent_5.min()) / recent_5.mean()
        avg_vol_20 = volume.iloc[-20:].mean()
        avg_vol_5 = volume.iloc[-5:].mean()

        if range_pct < 0.03 and avg_vol_5 > avg_vol_20 * 1.3 and close.iloc[-1] <= high.iloc[-20:].max() * 0.99:
            signals.append("放量滞涨")
            score += 1

    # --- 4. HH/HL 结构破坏 ---
    from indicators.price_structure import identify_swing_points, check_trend_structure
    highs, lows = identify_swing_points(df, threshold=0.03)

    if len(lows) >= 3:
        recent_lows = sorted(lows, key=lambda x: str(x[0]))[-3:]
        if recent_lows[-1][1] < recent_lows[-2][1] * 0.98:
            signals.append("前低被跌破(HL失败)")
            score += 1

    level = min(score, 3)
    return level, signals, {
        "score": score,
        "signals": signals,
        "level": level,
    }


# ================================================================
#  P1: 加速检测 —— 冲顶预警
# ================================================================

def detect_acceleration(df, short_window=5, mid_window=20):
    """检测加速赶顶/赶底信号。

    加速 = 近期涨速 >> 中期涨速 + 成交量暴增

    返回:
        (is_accelerating: bool, direction: str, info: dict)
        direction: "up"(加速上涨/赶顶) / "down"(加速下跌/赶底)
    """
    if len(df) < mid_window + short_window:
        return False, "none", {"reason": "数据不足"}

    close = df["close"]
    volume = df["volume"]

    # 短期涨速 vs 中期涨速
    short_ret = close.iloc[-1] / close.iloc[-short_window] - 1
    mid_ret = close.iloc[-short_window] / close.iloc[-mid_window] - 1 if len(close) >= mid_window else 0

    short_daily = short_ret / short_window
    mid_daily = mid_ret / (mid_window - short_window) if (mid_window - short_window) > 0 else 0.001

    accel_ratio = short_daily / mid_daily if abs(mid_daily) > 0.0001 else 1.0

    # 成交量验证
    vol_short = volume.iloc[-short_window:].mean()
    vol_mid = volume.iloc[-mid_window:-short_window].mean()
    vol_ratio = vol_short / vol_mid if vol_mid > 0 else 1.0

    # 判断条件
    direction = "none"
    is_accel = False

    if short_ret > 0 and accel_ratio > 1.8 and vol_ratio > 1.3:
        direction = "up"
        is_accel = True
    elif short_ret < 0 and accel_ratio > 1.8 and vol_ratio > 1.3:
        direction = "down"
        is_accel = True

    return is_accel, direction, {
        "short_ret": round(short_ret * 100, 2),
        "mid_ret": round(mid_ret * 100, 2),
        "accel_ratio": round(accel_ratio, 2),
        "vol_ratio": round(vol_ratio, 2),
    }


# ================================================================
#  P1: 回调 vs 反转 —— 道氏确认
# ================================================================

def classify_pullback_vs_reversal(df, primary_up=True):
    """区分回调还是反转。

    使用道氏理论关键判定:
      反转: 价格跌破上一个显著低点（HL失败） + 反弹无力
      回调: 价格未破前低 + 均线保持多头排列

    返回:
        (classification: str, info: dict)
        classification: "回调" / "可能反转" / "确认反转"
    """
    if len(df) < 60:
        return "数据不足", {}

    from indicators.price_structure import identify_swing_points

    close = df["close"]
    high = df["high"]

    swings_high, swings_low = identify_swing_points(df, threshold=0.03)
    adx_val, p, m = calc_adx(df.iloc[-40:], period=14)

    info = {"adx": round(adx_val, 1)}

    if not primary_up:
        return "非上升趋势", info

    # 检查前低是否被跌破
    if len(swings_low) >= 2:
        last_low = swings_low[-1][1]
        prev_low = swings_low[-2][1]
        low_broken = last_low < prev_low * 0.98
        info["last_low"] = round(last_low, 2)
        info["prev_low"] = round(prev_low, 2)
        info["low_broken"] = low_broken
    else:
        low_broken = False

    # 反弹力度
    recent_high = high.iloc[-20:].max()
    peak_60 = high.iloc[-60:].max()
    rebound_strength = recent_high / peak_60 if peak_60 > 0 else 0
    info["rebound_strength"] = round(rebound_strength, 3)

    # 均线状态
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    ma_bearish = pd.notna(ma20) and pd.notna(ma60) and ma20 < ma60
    info["ma_bearish"] = ma_bearish

    # 综合判断
    if low_broken and rebound_strength < 0.85:
        return "确认反转", info
    elif low_broken or (ma_bearish and adx_val < 20):
        return "可能反转", info
    else:
        return "回调", info


# ================================================================
#  工具函数：ATR
# ================================================================

def atr(df, period=14):
    """计算平均真实波幅。"""
    if len(df) < period:
        return 0.0
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])
