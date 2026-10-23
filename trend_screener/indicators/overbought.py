"""
过热/超买检测 —— 多维复合信号

与 detect_top_exhaustion（趋势末端）不同，本模块侧重判断"当前价位是否过热，
不适合新建仓位"。趋势可以继续，但此处入场风险回报比差。

输出不是"卖出"，而是"谨慎入场 / 等回调"。
"""

import numpy as np
import pandas as pd


# ================================================================
#  RSI —— Wilder 经典算法
# ================================================================

def rsi(df, period=14):
    """计算 RSI(14)。

    返回: float 0~100
    """
    if len(df) < period + 1:
        return 50.0

    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - 100.0 / (1.0 + rs), 1)


# ================================================================
#  Bollinger %B —— 价格在布林带中的位置
# ================================================================

def bollinger_pct_b(df, period=20, nbdev=2.0):
    """计算 Bollinger %B。

    %B > 1.0 = 价格突破上轨（极端强势）
    %B < 0   = 价格跌破下轨

    返回:
        float
    """
    if len(df) < period:
        return 0.5

    close = df["close"]
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + nbdev * std
    lower = middle - nbdev * std

    u, l, c = upper.iloc[-1], lower.iloc[-1], close.iloc[-1]
    if pd.isna(u) or pd.isna(l) or u == l:
        return 0.5

    return round(float((c - l) / (u - l)), 3)


# ================================================================
#  距离 MA 偏离度
# ================================================================

def ma_deviation(df, ma_period=20):
    """价格偏离 MA 的百分比。

    正值 = 价格高于均线（短期过热风险）
    负值 = 价格低于均线（可能超卖）

    返回:
        float: 如 0.15 表示价格高于 MA 15%
    """
    if len(df) < ma_period:
        return 0.0

    close = df["close"]
    ma = close.rolling(ma_period).mean().iloc[-1]
    if pd.isna(ma) or ma == 0:
        return 0.0
    return round(float(close.iloc[-1] / ma - 1.0), 4)


# ================================================================
#  成交量高潮 —— 放量冲顶信号
# ================================================================

def volume_climax(df, vol_window=20, vol_multiplier=2.0):
    """检测是否出现放量高潮（Volume Climax）。

    巨量 + 价格冲高 = 可能是派发，不是健康上涨。

    返回:
        (is_climax: bool, vol_ratio: float)
    """
    if len(df) < vol_window + 5:
        return False, 1.0

    volume = df["volume"]
    close = df["close"]

    avg_vol = volume.iloc[-vol_window:].mean()
    latest_vol = volume.iloc[-1]

    if avg_vol == 0:
        return False, 1.0

    ratio = latest_vol / avg_vol

    # 巨量 + 价格在近期高位
    high_n = df["high"].iloc[-vol_window:].max()
    is_high = close.iloc[-1] >= high_n * 0.97  # 最近在最高点3%以内

    return (ratio > vol_multiplier and is_high), round(ratio, 2)


# ================================================================
#  短期涨速（ROC）—— 涨太快了
# ================================================================

def rate_of_change(df, period=10):
    """计算短期涨速。

    返回:
        float: 如 0.25 表示近10天涨了25%
    """
    if len(df) < period:
        return 0.0

    close = df["close"]
    return round(float(close.iloc[-1] / close.iloc[-period] - 1.0), 4)


# ================================================================
#  综合过热评分 —— 核心函数
# ================================================================

def overbought_score(df):
    """多维过热综合评分。

    综合 RSI、%B、MA偏离、放量高潮、短期涨速五个维度，
    输出 0~1 之间的过热得分。

    得分解读:
      0.0 ~ 0.3  正常，可入场
      0.3 ~ 0.5  偏高，注意
      0.5 ~ 0.7  过热，等回调再入场
      0.7 ~ 1.0  严重过热，远离

    返回:
        dict: {
            "score": float 0~1,
            "level": str,       # "正常" / "偏高" / "过热" / "严重过热"
            "details": {...},   # 各维度明细
            "warnings": [...],  # 触发的警告项
        }
    """
    details = {}
    warnings = []
    score = 0.0
    max_score = 5.0  # 五项各贡献最多1分

    # --- 1. RSI (权重1) ---
    rsi_val = rsi(df)
    details["RSI(14)"] = rsi_val
    if rsi_val > 80:
        score += 1.0
        warnings.append(f"RSI={rsi_val}(严重超买)")
    elif rsi_val > 70:
        score += 0.6
        warnings.append(f"RSI={rsi_val}(超买)")
    elif rsi_val > 60:
        score += 0.2

    # --- 2. Bollinger %B (权重1) ---
    pct_b = bollinger_pct_b(df)
    details["%B"] = pct_b
    if pct_b > 1.0:
        score += 1.0
        warnings.append(f"价格突破布林上轨(%B={pct_b})")
    elif pct_b > 0.85:
        score += 0.6
    elif pct_b > 0.7:
        score += 0.2

    # --- 3. MA偏离度 (权重1) ---
    dev = ma_deviation(df)
    details["MA20偏离"] = f"{dev*100:.1f}%"
    if dev > 0.20:
        score += 1.0
        warnings.append(f"价格高于MA20 {dev*100:.0f}%(严重偏离)")
    elif dev > 0.12:
        score += 0.6
        warnings.append(f"价格高于MA20 {dev*100:.0f}%")
    elif dev > 0.06:
        score += 0.2

    # --- 4. 放量高潮 (权重1) ---
    is_climax, vol_ratio = volume_climax(df)
    details["放量高潮"] = f"量比{vol_ratio:.1f}"
    if is_climax:
        score += 1.0
        warnings.append(f"放量高潮(量比{vol_ratio:.1f})")
    elif vol_ratio > 1.5:
        score += 0.3

    # --- 5. 短期涨速 (权重1) ---
    roc = rate_of_change(df)
    details["10日涨速"] = f"{roc*100:.1f}%"
    if roc > 0.30:
        score += 1.0
        warnings.append(f"10日涨速{roc*100:.0f}%(急涨)")
    elif roc > 0.18:
        score += 0.6
    elif roc > 0.10:
        score += 0.2

    # 归一化到 0~1
    score = round(min(score / max_score, 1.0), 2)

    # 等级
    if score >= 0.7:
        level = "严重过热"
    elif score >= 0.5:
        level = "过热"
    elif score >= 0.3:
        level = "偏高"
    else:
        level = "正常"

    return {
        "score": score,
        "level": level,
        "details": details,
        "warnings": warnings,
    }
