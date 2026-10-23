"""
多时间尺度趋势评估引擎 —— 道氏理论三层趋势框架（可调参版 v2）

核心逻辑：
  - 主要趋势（Primary / 长期）：周线级别 → 决定做多方向
  - 次级趋势（Secondary / 中期）：日线中期 → 定位当前阶段
  - 小型趋势（Minor / 短期）：日线短期 → 把握入场时机

v2 改动：所有评分函数的关键阈值均可通过参数传入，不再硬绑 config.py。
         evaluate_trend 保持向后兼容（不传参=用 config 默认值）。
"""

import pandas as pd
import numpy as np

from config import (
    PRIMARY_TREND, SECONDARY_TREND, MINOR_TREND, TREND_STATE_MATRIX,
)
from indicators.trend_strength import ma_alignment_score, adx, ma_slope
from indicators.price_structure import identify_swing_points, check_trend_structure


# ---- 工具：日线→周线 ----

def daily_to_weekly(df_daily):
    if df_daily is None or df_daily.empty:
        return pd.DataFrame()
    df = df_daily.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    avail = [c for c in ["open", "high", "low", "close"] if c in df.columns]
    if len(avail) < 4:
        return pd.DataFrame()
    weekly = df.resample("W").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    })
    if "volume" in df.columns:
        weekly["volume"] = df["volume"].resample("W").sum()
    return weekly.dropna()


# ================================================================
#  主要趋势（Primary / 长期）—— 周线
# ================================================================

def score_primary_trend(df_daily,
                        ma_periods=None, adx_period=None, adx_threshold=None,
                        swing_threshold=None, min_score=None):
    """长期趋势评分（周线）。不传参则用 config 默认值。"""
    cfg = PRIMARY_TREND
    ma_p = ma_periods or cfg["ma_periods"]
    adx_p = adx_period or cfg["adx_period"]
    adx_t = adx_threshold or cfg["adx_threshold"]
    sw_t = swing_threshold or cfg["swing_threshold"]
    min_s = min_score or cfg["min_score"]

    df_weekly = daily_to_weekly(df_daily)
    if len(df_weekly) < 40:
        return 0.0, False

    score = 0.0
    close_w = df_weekly["close"]

    align = ma_alignment_score(df_weekly, ma_periods=ma_p, window=20)
    if align > 0:
        score += 1.0
    elif align > 0.3:
        score += 0.5

    adx_val, plus_di, minus_di = adx(df_weekly, period=adx_p)
    if adx_val > adx_t and plus_di > minus_di:
        score += min(adx_val / 50.0, 1.0)

    highs, lows = identify_swing_points(df_weekly, threshold=sw_t)
    structure_ok, quality = check_trend_structure(highs, lows, min_swings=2)
    if structure_ok:
        score += 0.5 + 0.5 * min(quality / 3.0, 1.0)

    ma_long = close_w.rolling(ma_p[-1]).mean().iloc[-1]
    if pd.notna(ma_long) and close_w.iloc[-1] > ma_long:
        score += 0.5

    return round(score, 2), score >= min_s


# ================================================================
#  次级趋势（Secondary / 中期）—— 日线
# ================================================================

def score_secondary_trend(df_daily,
                          ma_periods=None, adx_period=None, adx_threshold=None,
                          swing_threshold=None, min_score=None,
                          drawdown_strong=None, drawdown_neutral=None):
    """中期趋势评分（日线中期均线）。不传参则用 config 默认值。"""
    cfg = SECONDARY_TREND
    ma_p = ma_periods or cfg["ma_periods"]
    adx_p = adx_period or cfg["adx_period"]
    adx_t = adx_threshold or cfg["adx_threshold"]
    sw_t = swing_threshold or cfg["swing_threshold"]
    min_s = min_score or cfg["min_score"]
    dd_s = drawdown_strong or cfg["drawdown_strong"]
    dd_n = drawdown_neutral or cfg["drawdown_neutral"]

    if len(df_daily) < max(ma_p) + 40:
        return 0.0, False

    score = 0.0
    close = df_daily["close"]

    align = ma_alignment_score(df_daily, ma_periods=ma_p, window=40)
    if align > 0:
        score += 1.0 - (1.0 - align) * 0.5
    elif align > 0.3:
        score += 0.3

    adx_val, plus_di, minus_di = adx(df_daily, period=adx_p)
    if adx_val > adx_t:
        if plus_di > minus_di:
            score += min(adx_val / 40.0, 1.0)
        else:
            score -= 0.5

    slope = ma_slope(df_daily, period=20, slope_window=10)
    if slope > 0:
        score += 0.5
    elif slope < -0.01:
        score -= 0.5

    ma60 = close.rolling(60).mean().iloc[-1]
    if pd.notna(ma60) and close.iloc[-1] > ma60:
        score += 0.5

    recent_high = df_daily["high"].rolling(60).max().iloc[-1]
    current = close.iloc[-1]
    if pd.notna(recent_high) and recent_high > 0:
        drawdown = (recent_high - current) / recent_high
        if drawdown < dd_s:
            score += 0.5
        elif drawdown < dd_n:
            score += 0.2

    return round(score, 2), score >= min_s


# ================================================================
#  小型趋势（Minor / 短期）—— 日线短期
# ================================================================

def score_minor_trend(df_daily,
                      ma_periods=None, adx_period=None, adx_threshold=None,
                      min_score=None):
    """短期趋势评分（日线短期均线+形态）。不传参则用 config 默认值。"""
    cfg = MINOR_TREND
    ma_p = ma_periods or cfg["ma_periods"]
    adx_p = adx_period or cfg["adx_period"]
    adx_t = adx_threshold or cfg["adx_threshold"]
    min_s = min_score or cfg["min_score"]

    if len(df_daily) < 20:
        return 0.0, False

    score = 0.0
    close = df_daily["close"]

    align = ma_alignment_score(df_daily, ma_periods=ma_p, window=10)
    if align > 0:
        score += 1.0
    elif align > 0.3:
        score += 0.3

    adx_val, plus_di, minus_di = adx(df_daily, period=adx_p)
    if adx_val > adx_t and plus_di > minus_di:
        score += 0.5

    closes_recent = close.iloc[-4:] if len(close) >= 4 else close
    if len(closes_recent) >= 3:
        consec_up = all(closes_recent.iloc[i] > closes_recent.iloc[i - 1]
                        for i in range(-(len(closes_recent) - 1), 0))
        if consec_up:
            score += 0.5

    if len(df_daily) >= 6:
        high_5d = df_daily["high"].iloc[-6:-1].max()
        if close.iloc[-1] > high_5d:
            score += 0.5

    ma10 = close.rolling(10).mean().iloc[-1]
    if pd.notna(ma10) and close.iloc[-1] > ma10:
        score += 0.5

    score = min(score, 3.0)
    return round(score, 2), score >= min_s


# ================================================================
#  三层综合评估 —— 核心入口
# ================================================================

def evaluate_trend(df_daily,
                   # 权重参数
                   primary_weight=None, secondary_weight=None, minor_weight=None,
                   # 主要趋势参数
                   prim_ma_periods=None, prim_adx_period=None,
                   prim_adx_threshold=None, prim_swing_threshold=None,
                   prim_min_score=None,
                   # 次级趋势参数
                   sec_ma_periods=None, sec_adx_period=None,
                   sec_adx_threshold=None, sec_swing_threshold=None,
                   sec_min_score=None, sec_drawdown_strong=None,
                   sec_drawdown_neutral=None,
                   # 小型趋势参数
                   min_ma_periods=None, min_adx_period=None,
                   min_adx_threshold=None, min_min_score=None,
                   verbose=False):
    """三时间尺度趋势综合评估 —— 整个系统的核心函数。

    对所有标的统一使用此函数（大盘/行业/个股）。

    参数中所有 None 表示使用 config.py 默认值。传入具体值即可覆盖。

    调用示例:
      # 使用默认配置
      evaluate_trend(df)

      # 个股更敏感（降低长期权重、放宽短期阈值）
      evaluate_trend(df, primary_weight=0.40, minor_weight=0.30,
                     prim_adx_threshold=20, min_adx_threshold=15)

      # 大盘更保守（提高阈值）
      evaluate_trend(df, prim_adx_threshold=28, sec_adx_threshold=25)
    """
    if df_daily is None or len(df_daily) < 120:
        return _empty_result()

    prim_score, prim_up = score_primary_trend(
        df_daily,
        ma_periods=prim_ma_periods, adx_period=prim_adx_period,
        adx_threshold=prim_adx_threshold, swing_threshold=prim_swing_threshold,
        min_score=prim_min_score,
    )
    sec_score, sec_up = score_secondary_trend(
        df_daily,
        ma_periods=sec_ma_periods, adx_period=sec_adx_period,
        adx_threshold=sec_adx_threshold, swing_threshold=sec_swing_threshold,
        min_score=sec_min_score, drawdown_strong=sec_drawdown_strong,
        drawdown_neutral=sec_drawdown_neutral,
    )
    min_score_val, min_up = score_minor_trend(
        df_daily,
        ma_periods=min_ma_periods, adx_period=min_adx_period,
        adx_threshold=min_adx_threshold, min_score=min_min_score,
    )

    w_prim = primary_weight if primary_weight is not None else PRIMARY_TREND["weight"]
    w_sec = secondary_weight if secondary_weight is not None else SECONDARY_TREND["weight"]
    w_min = minor_weight if minor_weight is not None else MINOR_TREND["weight"]

    total = (w_prim * prim_score / 4.0 +
             w_sec * sec_score / 4.0 +
             w_min * min_score_val / 3.0)

    consensus = sum([prim_up, sec_up, min_up])
    if consensus == 3:
        total += 0.08
    elif consensus == 0:
        total -= 0.08
    elif consensus == 1 and prim_up:
        total -= 0.03

    total = round(max(min(total, 1.0), 0.0), 3)

    state, action = TREND_STATE_MATRIX.get(
        (prim_up, sec_up, min_up), ("未知", "NO_TRADE"))

    result = {
        "primary_score": prim_score, "secondary_score": sec_score,
        "minor_score": min_score_val, "total_score": total,
        "prim_up": prim_up, "sec_up": sec_up, "min_up": min_up,
        "state": state, "action": action,
    }
    if verbose:
        _print_eval(result)
    return result


def _empty_result():
    return {
        "primary_score": 0.0, "secondary_score": 0.0, "minor_score": 0.0,
        "total_score": 0.0, "prim_up": False, "sec_up": False, "min_up": False,
        "state": "数据不足", "action": "NO_TRADE",
    }


def _print_eval(result):
    bar_p = "█" * int(result["primary_score"])
    bar_s = "█" * int(result["secondary_score"])
    bar_m = "█" * int(result["minor_score"])
    a_p = "↑" if result["prim_up"] else "↓"
    a_s = "↑" if result["sec_up"] else "↓"
    a_m = "↑" if result["min_up"] else "↓"
    print(f"  长期(周线) [{result['primary_score']:.1f}/4] {bar_p} {a_p}")
    print(f"  中期(日线) [{result['secondary_score']:.1f}/4] {bar_s} {a_s}")
    print(f"  短期(日线) [{result['minor_score']:.1f}/3] {bar_m} {a_m}")
    print(f"  → {result['total_score']:.3f} | {result['state']} | {result['action']}")
