"""
图表形态识别 —— 反转形态 + 持续形态

基于波段高低点（zigzag）识别经典技术形态。

反转形态: 头肩顶/底、双顶/底、圆顶、V顶
持续形态: 三角形（对称/上升/下降）、楔形（上升/下降）

全部独立函数，输入 DataFrame，输出检测结果 dict。
"""

import numpy as np
import pandas as pd
from indicators.price_structure import identify_swing_points


# ================================================================
#  工具：趋势线拟合
# ================================================================

def _fit_line(points):
    """对 [(x, y), ...] 做最小二乘拟合，返回 (slope, intercept, r_squared)。"""
    if len(points) < 2:
        return 0, 0, 0
    xs = np.array([i for i, _ in enumerate(points)], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    A = np.vstack([xs, np.ones_like(xs)]).T
    try:
        slope, intercept = np.linalg.lstsq(A, ys, rcond=None)[0]
    except np.linalg.LinAlgError:
        return 0, 0, 0
    pred = slope * xs + intercept
    ss_res = np.sum((ys - pred) ** 2)
    ss_tot = np.sum((ys - ys.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    return slope, intercept, r2


def _price_similar(p1, p2, tolerance=0.03):
    """两个价格是否在 tolerance 范围内接近。"""
    if p1 == 0:
        return False
    return abs(p1 - p2) / abs(p1) < tolerance


# ================================================================
#  头肩顶 / 头肩底
# ================================================================

def detect_head_shoulders(df, threshold=0.04, tolerance=0.03):
    """检测头肩顶和头肩底形态。

    头肩顶: 左肩 < 头 > 右肩 ≈ 左肩, 颈线连接两个谷
    头肩底: 左肩 > 头 < 右肩 ≈ 左肩, 颈线连接两个峰

    返回:
        dict: {found, type, confidence, points, neckline, target}
    """
    if len(df) < 80:
        return _no_pattern()

    highs, lows = identify_swing_points(df, threshold=threshold)
    if len(highs) < 3 or len(lows) < 2:
        return _no_pattern()

    result = _no_pattern()

    # --- 头肩顶: 检查最近5个波段高点 ---
    h = sorted(highs, key=lambda x: str(x[0]))[-5:]
    l = sorted(lows, key=lambda x: str(x[0]))[-5:]

    # 头肩顶: 取连续三个峰
    for i in range(len(h) - 2):
        left = h[i]
        head = h[i + 1]
        right = h[i + 2]

        # 条件1: 头高于两肩
        if not (head[1] > left[1] and head[1] > right[1]):
            continue
        # 条件2: 两肩高度接近
        if not _price_similar(left[1], right[1], tolerance):
            continue
        # 条件3: 时间对称（头到两肩的时间差不能差太多）
        time_l = pd.Timestamp(head[0]) - pd.Timestamp(left[0])
        time_r = pd.Timestamp(right[0]) - pd.Timestamp(head[0])
        if time_r.days == 0:
            continue
        ratio = time_l.days / time_r.days if time_r.days > 0 else 999
        if not (0.4 < ratio < 2.5):
            continue

        # 找颈线（两肩之间的最低谷）
        neck_val = head[1] * 0.85  # 默认颈线在头下方15%
        neck_pts = [x for x in l if str(min(left[0], right[0])) <= str(x[0]) <= str(max(right[0], left[0]))]
        if neck_pts:
            neck_val = min(x[1] for x in neck_pts)

        # 量度跌幅 = 头 - 颈线
        target = neck_val - (head[1] - neck_val)

        conf = min(0.95, 0.5 + _price_similar(left[1], right[1], 0.015) * 0.3
                   + (1 - abs(1 - ratio) / 5) * 0.15)
        return {
            "found": True,
            "type": "头肩顶",
            "confidence": round(conf, 2),
            "head": round(head[1], 2),
            "left_shoulder": round(left[1], 2),
            "right_shoulder": round(right[1], 2),
            "neckline": round(neck_val, 2),
            "target": round(max(target, 0), 2),
            "head_date": str(head[0])[:10],
        }

    # --- 头肩底: 检查最近5个波段低点 ---
    for i in range(len(l) - 2):
        left = l[i]
        head = l[i + 1]
        right = l[i + 2]

        if not (head[1] < left[1] and head[1] < right[1]):
            continue
        if not _price_similar(left[1], right[1], tolerance):
            continue

        time_l = pd.Timestamp(head[0]) - pd.Timestamp(left[0])
        time_r = pd.Timestamp(right[0]) - pd.Timestamp(head[0])
        if time_r.days == 0:
            continue
        ratio = time_l.days / time_r.days
        if not (0.4 < ratio < 2.5):
            continue

        neck_pts = [x for x in h if str(min(left[0], right[0])) <= str(x[0]) <= str(max(right[0], left[0]))]
        neck_val = head[1] * 1.15
        if neck_pts:
            neck_val = max(x[1] for x in neck_pts)

        target = neck_val + (neck_val - head[1])
        conf = min(0.95, 0.5 + _price_similar(left[1], right[1], 0.015) * 0.3
                   + (1 - abs(1 - ratio) / 5) * 0.15)
        return {
            "found": True,
            "type": "头肩底",
            "confidence": round(conf, 2),
            "head": round(head[1], 2),
            "left_shoulder": round(left[1], 2),
            "right_shoulder": round(right[1], 2),
            "neckline": round(neck_val, 2),
            "target": round(target, 2),
            "head_date": str(head[0])[:10],
        }

    return _no_pattern()


# ================================================================
#  双顶 / 双底
# ================================================================

def detect_double_top_bottom(df, threshold=0.03, tolerance=0.02):
    """检测双顶/双底形态。

    双顶: 两个相近高度的峰，间隔适当
    双底: 两个相近深度的谷，间隔适当

    返回:
        dict
    """
    if len(df) < 40:
        return _no_pattern()

    highs, lows = identify_swing_points(df, threshold=threshold)
    if len(highs) < 2 and len(lows) < 2:
        return _no_pattern()

    close = df["close"].iloc[-1]

    # --- 双顶 ---
    h = sorted(highs, key=lambda x: str(x[0]))[-4:]
    for i in range(len(h) - 1):
        top1 = h[i]
        top2 = h[i + 1]

        if not _price_similar(top1[1], top2[1], tolerance):
            continue

        # 两个顶之间至少有 10 个交易日
        try:
            days_between = (pd.Timestamp(top2[0]) - pd.Timestamp(top1[0])).days
        except Exception:
            days_between = 0
        if days_between < 10 or days_between > 90:
            continue

        # 找中间谷底
        mid_lows = [x for x in lows
                    if str(top1[0]) <= str(x[0]) <= str(top2[0])]
        valley = min(x[1] for x in mid_lows) if mid_lows else min(top1[1], top2[1]) * 0.9

        # 确认颈线跌破
        neckline_broken = close < valley * 0.99

        # 量度跌幅
        target = valley - (top1[1] - valley)

        return {
            "found": True,
            "type": "双顶",
            "confidence": round(min(0.9, 0.5 + neckline_broken * 0.3
                                     + _price_similar(top1[1], top2[1], 0.01) * 0.1), 2),
            "top1": round(top1[1], 2),
            "top2": round(top2[1], 2),
            "valley": round(valley, 2),
            "neckline_broken": neckline_broken,
            "target": round(max(target, 0), 2),
            "days_between": days_between,
        }

    # --- 双底 ---
    l = sorted(lows, key=lambda x: str(x[0]))[-4:]
    for i in range(len(l) - 1):
        bot1 = l[i]
        bot2 = l[i + 1]

        if not _price_similar(bot1[1], bot2[1], tolerance):
            continue
        try:
            days_between = (pd.Timestamp(bot2[0]) - pd.Timestamp(bot1[0])).days
        except Exception:
            days_between = 0
        if days_between < 10 or days_between > 90:
            continue

        mid_highs = [x for x in highs
                     if str(bot1[0]) <= str(x[0]) <= str(bot2[0])]
        peak = max(x[1] for x in mid_highs) if mid_highs else max(bot1[1], bot2[1]) * 1.1

        neckline_broken = close > peak * 1.01
        target = peak + (peak - bot1[1])

        return {
            "found": True,
            "type": "双底",
            "confidence": round(min(0.9, 0.5 + neckline_broken * 0.3
                                     + _price_similar(bot1[1], bot2[1], 0.01) * 0.1), 2),
            "bottom1": round(bot1[1], 2),
            "bottom2": round(bot2[1], 2),
            "peak": round(peak, 2),
            "neckline_broken": neckline_broken,
            "target": round(target, 2),
            "days_between": days_between,
        }

    return _no_pattern()


# ================================================================
#  V 顶 — 急涨急跌
# ================================================================

def detect_v_top(df, lookback=30, rise_threshold=0.10, fall_threshold=0.07):
    """检测 V 形反转（V顶/V底）。

    V顶: 近 N 日急涨 > rise_threshold 后快速回落 > fall_threshold
    V底: 近 N 日急跌后快速反弹

    返回:
        dict
    """
    if len(df) < lookback:
        return _no_pattern()

    close = df["close"]

    # 找 lookback 内的最高点和最低点
    half = lookback // 2
    first = close.iloc[-lookback:-half]
    second = close.iloc[-half:]

    # V 顶: 先涨后跌
    first_ret = second.iloc[0] / first.iloc[-1] - 1
    second_ret = second.iloc[-1] / second.iloc[0] - 1

    if first_ret > rise_threshold and second_ret < -fall_threshold:
        return {
            "found": True,
            "type": "V顶",
            "confidence": round(min(0.9, 0.5 + abs(second_ret) / 0.15), 2),
            "rise_pct": round(first_ret * 100, 1),
            "fall_pct": round(second_ret * 100, 1),
            "peak": round(max(close.iloc[-half:].max(), second.iloc[0]), 2),
        }

    # V 底: 先跌后涨
    if first_ret < -rise_threshold and second_ret > fall_threshold:
        return {
            "found": True,
            "type": "V底",
            "confidence": round(min(0.9, 0.5 + second_ret / 0.15), 2),
            "fall_pct": round(first_ret * 100, 1),
            "rise_pct": round(second_ret * 100, 1),
            "valley": round(min(close.iloc[-half:].min(), second.iloc[0]), 2),
        }

    return _no_pattern()


# ================================================================
#  圆顶（简化版——用曲率变化判断）
# ================================================================

def detect_rounding_top(df, lookback=60, curve_threshold=5):
    """检测圆形顶（简化版）。

    逻辑: 价格以递减的速度上涨，然后以递增的速度下跌——形成弧形。

    通过计算二次导数来检测曲率变化。

    返回:
        dict
    """
    if len(df) < lookback:
        return _no_pattern()

    close = df["close"].iloc[-lookback:].values
    n = len(close)

    # 用二次多项式拟合
    x = np.arange(n)
    coeffs = np.polyfit(x, close, 2)
    a = coeffs[0]  # 二次项系数

    # 二次项为负 = 向下弯曲的弧线（圆顶特征）
    # 同时需要价格在较高位
    recent_high = np.max(close[-20:])
    all_high = np.max(close)

    if a < -0.001 and recent_high > all_high * 0.95:
        curvature = abs(a) * 1000
        return {
            "found": True,
            "type": "圆顶",
            "confidence": round(min(0.85, 0.3 + curvature / 20), 2),
            "curvature": round(curvature, 2),
            "peak": round(all_high, 2),
            "current": round(close[-1], 2),
            "decline_from_peak": round((1 - close[-1] / all_high) * 100, 1),
        }

    elif a > 0.001:
        # 向上弯曲 = 圆底特征
        recent_low = np.min(close[-20:])
        all_low = np.min(close)
        if recent_low < all_low * 1.05:
            curvature = abs(a) * 1000
            return {
                "found": True,
                "type": "圆底",
                "confidence": round(min(0.85, 0.3 + curvature / 20), 2),
                "curvature": round(curvature, 2),
                "valley": round(all_low, 2),
                "current": round(close[-1], 2),
                "rise_from_valley": round((close[-1] / all_low - 1) * 100, 1),
            }

    return _no_pattern()


# ================================================================
#  三角形 / 楔形（持续形态）
# ================================================================

def detect_triangle_wedge(df, threshold=0.03, lookback_swings=8):
    """检测三角形和楔形持续形态。

    三角形: 趋势线收敛（高点连线下降 + 低点连线上升 = 对称三角形）
    上升三角形: 高点水平 + 低点上升
    下降三角形: 低点水平 + 高点下降
    楔形: 两条趋势线同向收敛

    返回:
        dict
    """
    if len(df) < 60:
        return _no_pattern()

    highs, lows = identify_swing_points(df, threshold=threshold)
    if len(highs) < 3 or len(lows) < 3:
        return _no_pattern()

    h = sorted(highs, key=lambda x: str(x[0]))[-lookback_swings:]
    l = sorted(lows, key=lambda x: str(x[0]))[-lookback_swings:]

    # 拟合上轨和下轨
    h_slope, _, h_r2 = _fit_line(h)
    l_slope, _, l_r2 = _fit_line(l)

    if h_r2 < 0.5 or l_r2 < 0.5:
        return _no_pattern()

    # 分类
    result = {"found": False, "info": {"h_slope": round(h_slope, 4), "l_slope": round(l_slope, 4)}}

    if h_slope < -0.01 and abs(l_slope) < 0.005:
        # 高点下降 + 低点平 → 下降三角形（看跌持续）
        result.update({
            "found": True,
            "type": "下降三角形",
            "direction": "bearish",
            "confidence": round(min(0.85, 0.5 + h_r2 * 0.35), 2),
        })
    elif abs(h_slope) < 0.005 and l_slope > 0.01:
        # 高点平 + 低点上升 → 上升三角形（看涨持续）
        result.update({
            "found": True,
            "type": "上升三角形",
            "direction": "bullish",
            "confidence": round(min(0.85, 0.5 + l_r2 * 0.35), 2),
        })
    elif h_slope < -0.01 and l_slope > 0.01:
        # 高点下降 + 低点上升 → 对称三角形（突破方向不确定）
        result.update({
            "found": True,
            "type": "对称三角形",
            "direction": "neutral",
            "confidence": round(min(0.80, 0.4 + (h_r2 + l_r2) / 2 * 0.4), 2),
        })
    elif h_slope < -0.01 and l_slope < -0.01 and h_slope < l_slope:
        # 两线同向下降，上轨更陡 → 下降楔形（看涨反转）
        result.update({
            "found": True,
            "type": "下降楔形",
            "direction": "bullish_reversal",
            "confidence": round(min(0.80, 0.5 + abs(h_slope - l_slope) * 50), 2),
        })
    elif h_slope > 0.01 and l_slope > 0.01 and h_slope > l_slope:
        # 两线同向上升，下轨更陡 → 上升楔形（看跌反转）
        result.update({
            "found": True,
            "type": "上升楔形",
            "direction": "bearish_reversal",
            "confidence": round(min(0.80, 0.5 + abs(h_slope - l_slope) * 50), 2),
        })

    if result["found"]:
        result["h_r2"] = round(h_r2, 2)
        result["l_r2"] = round(l_r2, 2)

    return result


# ================================================================
#  综合形态检测
# ================================================================

def detect_all_patterns(df):
    """对一只标的运行全部形态检测。

    返回:
        dict: {pattern_type: result, ...}
    """
    patterns = {}

    hs = detect_head_shoulders(df)
    if hs["found"]:
        patterns["head_shoulders"] = hs

    dt = detect_double_top_bottom(df)
    if dt["found"]:
        patterns["double"] = dt

    vt = detect_v_top(df)
    if vt["found"]:
        patterns["v_reversal"] = vt

    rt = detect_rounding_top(df)
    if rt["found"]:
        patterns["rounding"] = rt

    tw = detect_triangle_wedge(df)
    if tw["found"]:
        patterns["triangle_wedge"] = tw

    return patterns if patterns else {"none": _no_pattern()}


def _no_pattern():
    return {"found": False, "type": "无形态"}
