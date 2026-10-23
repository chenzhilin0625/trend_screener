"""
价格结构识别 —— 波段高低点（ZigZag 简化版） + HH/HL 多头结构判定。

道氏理论最基础的原理：多头趋势 = 更高的高点 + 更高的低点。
这个模块是趋势判断的"锚"。
"""


def identify_swing_points(df, threshold=0.04):
    """识别波段高低点。

    这是一个简化版的 ZigZag 算法：
    从一个极值点开始，只有当价格从极值反向运动超过 threshold 比例时，
    才确认一个波段转折点。

    参数:
        df: DataFrame, columns 至少包含 ['close']，index 为日期
        threshold: 反转幅度阈值（如 0.04 表示 4%）

    返回:
        (highs, lows):
            highs: list[(index, price)]  波段高点列表
            lows:  list[(index, price)]  波段低点列表
    """
    if len(df) < 5:
        return [], []

    close = df["close"]
    highs = []
    lows = []

    extreme_val = close.iloc[0]
    extreme_idx = 0
    direction = 0  # 0=初始, 1=上升段中, -1=下降段中

    for i in range(1, len(close)):
        price = close.iloc[i]
        idx = close.index[i]

        if direction == 0:
            # 初始状态：确定第一个方向
            if price > extreme_val * (1 + threshold):
                lows.append((close.index[extreme_idx], extreme_val))
                direction = 1
                extreme_val = price
                extreme_idx = i
            elif price < extreme_val * (1 - threshold):
                highs.append((close.index[extreme_idx], extreme_val))
                direction = -1
                extreme_val = price
                extreme_idx = i

        elif direction == 1:
            # 上升段：价格创新高 → 更新极值；回落超阈值 → 确认高转低
            if price > extreme_val:
                extreme_val = price
                extreme_idx = i
            elif price < extreme_val * (1 - threshold):
                highs.append((idx_of(i, close), extreme_val))
                direction = -1
                extreme_val = price
                extreme_idx = i

        else:  # direction == -1
            # 下降段：价格创新低 → 更新极值；反弹超阈值 → 确认低转高
            if price < extreme_val:
                extreme_val = price
                extreme_idx = i
            elif price > extreme_val * (1 + threshold):
                lows.append((idx_of(i, close), extreme_val))
                direction = 1
                extreme_val = price
                extreme_idx = i

    return highs, lows


def idx_of(i, close_series):
    """安全获取索引。"""
    if i < len(close_series):
        return close_series.index[i]
    return i


def check_trend_structure(highs, lows, min_swings=2):
    """检查价格结构是否符合多头趋势（HH + HL）。

    参数:
        highs: identify_swing_points 返回的高点列表
        lows: identify_swing_points 返回的低点列表
        min_swings: 最少需要几轮 HH+HL 才算有效趋势

    返回:
        (is_bullish_structure: bool, quality: int)
            quality 粗略表示结构有多"好"（轮数越多越可靠）
    """
    if len(highs) < min_swings or len(lows) < min_swings:
        return False, 0

    # 按时序排序，取最近 min_swings 个
    all_points = sorted(highs + lows, key=lambda x: str(x[0]))
    recent_highs = sorted(highs, key=lambda x: str(x[0]))[-min_swings:]
    recent_lows = sorted(lows, key=lambda x: str(x[0]))[-min_swings:]

    hh_vals = [h[1] for h in recent_highs]
    hl_vals = [l[1] for l in recent_lows]

    # 更高的高点
    higher_highs = all(
        hh_vals[i] > hh_vals[i-1] for i in range(1, len(hh_vals))
    )
    # 更高的低点
    higher_lows = all(
        hl_vals[i] > hl_vals[i-1] for i in range(1, len(hl_vals))
    )

    structure_ok = higher_highs and higher_lows

    # quality: 有多少轮完整的 HH+HL
    quality = min(len(highs), len(lows))

    return structure_ok, quality
