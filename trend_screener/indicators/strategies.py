"""
统一策略函数库 —— 趋势交易者每日复盘工具箱

所有函数遵循统一规范：
  1. 入参中将关键阈值作为函数参数，便于调参
  2. 注释说明技术分析原理和参数含义
  3. 返回标准 dict，包含 found/signal/level/info 等字段
  4. 独立、无副作用、可用于大盘/行业/个股任意标的

分类:
  A. 趋势识别         —— 判断趋势方向和强度
  B. 趋势质量         —— 区分真趋势/震荡/假突破
  C. 趋势阶段         —— 判断顶部/底部/加速/回调
  D. 形态识别         —— 经典技术形态
  E. 相对强度         —— 横截面排名
  F. 市场环境         —— 大盘宽度/广度
  G. 退出管理         —— 止损/止盈
  H. 行业轮动         —— 板块强弱转换
"""

import numpy as np
import pandas as pd

# ================================================================
#  A. 趋势识别
# ================================================================

# ---- A1. 日线→周线聚合 ----

def daily_to_weekly(df_daily):
    """将日线 OHLCV 聚合为周线。

    技术原理:
      周线过滤了日内噪音，更能反映中期资金意图。适合用于主要趋势分析。

    参数:
        df_daily: DataFrame, index=DatetimeIndex, columns=[open,high,low,close,volume]

    返回:
        DataFrame: 周线 OHLCV
    """
    if df_daily is None or df_daily.empty:
        return pd.DataFrame()
    df = df_daily.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    required = [c for c in ["open", "high", "low", "close"] if c in df.columns]
    if len(required) < 4:
        return pd.DataFrame()
    weekly = df.resample("W").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    })
    if "volume" in df.columns:
        weekly["volume"] = df["volume"].resample("W").sum()
    return weekly.dropna()


# ---- A2. ADX 趋势强度 ----
from indicators.trend_strength import adx as _adx_calc


def adx_trend_strength(df, period=14, strong_threshold=25, weak_threshold=20):
    """ADX 趋势强度评估。

    技术原理:
      ADX (Average Directional Index) 衡量趋势强度而不指示方向。值越高趋势越强。
      +DI > -DI 表示多头主导，反之空头主导。
      ADX < 20 → 震荡市，不适合趋势策略
      ADX 20-25 → 弱趋势，需更多确认
      ADX 25-40 → 明显趋势，可以跟随
      ADX > 40 → 强趋势，注意可能加速赶顶/底

    参数:
        df: DataFrame with high, low, close
        period: ADX 计算周期，默认14（Wilder经典值）
        strong_threshold: 强趋势阈值，默认25
        weak_threshold: 弱趋势/震荡阈值，默认20

    返回:
        dict: {adx, plus_di, minus_di, strength, direction, is_trending}
    """
    if len(df) < period * 2:
        return {"adx": 0, "plus_di": 0, "minus_di": 0, "strength": "数据不足", "direction": "unknown", "is_trending": False}

    a, p, m = _adx_calc(df, period=period)

    if a >= strong_threshold:
        strength = "强趋势" if a < 40 else "极强趋势(警惕衰竭)"
    elif a >= weak_threshold:
        strength = "弱趋势"
    else:
        strength = "震荡/无趋势"

    direction = "多头" if p > m else "空头"
    is_trending = a >= weak_threshold

    return {
        "adx": round(a, 1),
        "plus_di": round(p, 1),
        "minus_di": round(m, 1),
        "strength": strength,
        "direction": direction,
        "is_trending": is_trending,
    }


# ---- A3. 均线多头排列评分 ----
from indicators.trend_strength import ma_alignment_score as _ma_align


def ma_alignment(df, ma_periods=(5, 10, 20, 60, 120), window=40):
    """均线多头/空头排列评分。

    技术原理:
      均线多头排列（短周期>长周期）是趋势最直观的确认信号。
      统计过去 window 天内多头排列的天数占比，输出 -1(完美空头) ~ +1(完美多头)。

    参数:
        df: DataFrame with 'close'
        ma_periods: 均线周期元组，默认(5,10,20,60,120) 覆盖短中长
        window: 统计窗口天数

    返回:
        dict: {score, state, long_term_up}
    """
    score = _ma_align(df, ma_periods=list(ma_periods), window=window)

    if score > 0.5:
        state = "强多头排列"
    elif score > 0.2:
        state = "偏多"
    elif score > -0.2:
        state = "均线交织(方向不明)"
    elif score > -0.5:
        state = "偏空"
    else:
        state = "强空头排列"

    return {
        "score": round(score, 3),
        "state": state,
        "long_term_up": score > 0.2,
    }


# ---- A4. 三时间尺度趋势综合评估 ----
from indicators.multi_timeframe import evaluate_trend as _eval_trend


def trend_three_timeframe(df, primary_weight=0.50, secondary_weight=0.30, minor_weight=0.20):
    """三层趋势综合评估 —— 道氏理论框架（可调参版）。

    技术原理:
      长期(50%): 周线 MA(10,20,40) + ADX(10) + HH/HL → 决定做多方向
      中期(30%): 日线 MA(20,60,120) + ADX(20) + 回撤 → 定位当前阶段
      短期(20%): 日线 MA(5,10,20) + ADX(7) + 形态 → 把握入场时机

    参数:
        df:             日线 DataFrame（需≥250天）
        primary_weight: 长期权重，长线投资者可调至0.60
        secondary_weight:中期权重
        minor_weight:   短期权重，短线交易者可调至0.35

    返回:
        dict: {primary_score, secondary_score, minor_score, total_score,
               prim_up, sec_up, min_up, state, action}
    """
    return _eval_trend(
        df,
        primary_weight=primary_weight,
        secondary_weight=secondary_weight,
        minor_weight=minor_weight,
    )


# ---- A5. HH/HL 价格结构 ----
from indicators.price_structure import identify_swing_points, check_trend_structure as _check_struct


def price_structure(df, swing_threshold=0.04, min_swings=2):
    """价格结构分析 —— 道氏理论 HH/HL 判定。

    技术原理:
      上升趋势 = 更高的高点(HH) + 更高的低点(HL)
      下跌趋势 = 更低的高点(LH) + 更低的低点(LL)
      当 HL 失败（跌破前一个显著低点）→ 趋势可能反转

      使用简化 Zigzag 算法识别波段极值点，阈值决定反转确认的敏感度。

    参数:
        df: DataFrame with close
        swing_threshold: 波段反转确认阈值（价格反向运动比例），默认0.04(4%)
                         越小越敏感，越大越稳定
        min_swings: 最少需要几轮HH+HL才算有效趋势，默认2

    返回:
        dict: {is_bullish, quality, highs_count, lows_count, swing_points}
    """
    highs, lows = identify_swing_points(df, threshold=swing_threshold)
    ok, quality = _check_struct(highs, lows, min_swings=min_swings)

    return {
        "is_bullish": ok,
        "quality": quality,
        "highs_count": len(highs),
        "lows_count": len(lows),
        "high_swings": [(str(h[0])[:10], round(h[1], 2)) for h in highs[-3:]] if highs else [],
        "low_swings": [(str(l[0])[:10], round(l[1], 2)) for l in lows[-3:]] if lows else [],
    }


# ================================================================
#  B. 趋势质量
# ================================================================

from indicators.trend_quality import (
    is_ranging as _is_ranging,
    validate_breakout as _validate_breakout,
)


def oscillation_filter(df, adx_period=20, adx_threshold=20, consecutive_days=3):
    """震荡过滤器 —— 判断是否适合用趋势策略。

    技术原理:
      趋势策略在震荡市中会反复被止损，是亏损最大来源。
      震荡判定: ADX持续低于阈值 + ±DI频繁交叉(方向不明确)。
      ADX<20 时绝对不应用趋势策略——这是量化趋势跟踪领域的铁律。

    参数:
        df: DataFrame with high, low, close
        adx_period: ADX计算周期，默认20
        adx_threshold: 震荡判定阈值，默认20。越低越宽松（更多标的视为有趋势）
        consecutive_days: ADX需连续低于阈值的天数，默认3

    返回:
        dict: {is_ranging, should_avoid, adx_latest, info}
    """
    is_rng, info = _is_ranging(df, adx_period=adx_period, adx_threshold=adx_threshold,
                               consecutive_days=consecutive_days)
    return {
        "is_ranging": is_rng,
        "should_avoid_trend_strategy": is_rng,
        "adx_latest": info.get("adx_latest", 0),
        "info": info,
    }


def breakout_quality(df, key_level=None, volume_ratio=1.5, close_confirm_days=2, ma_period=20):
    """突破质量验证 —— 区分真突破和假突破。

    技术原理:
      假突破（Bull/Bear Trap）是最常见的亏损来源。
      真突破 = 价格突破关键位 + 成交量放大 + 连续收盘站稳。
      缺少成交量确认的突破大概率是假信号。
      "量在价先"——放量是真金白银的认可。

    参数:
        df: DataFrame with close, volume
        key_level: 关键价位（如前期高点）。None则自动用MA(ma_period)作参考
        volume_ratio: 突破日成交量需大于N日均量的倍数，默认1.5
        close_confirm_days: 需连续收盘站稳关键位的天数，默认2
        ma_period: 用作默认关键位的均线周期，默认20

    返回:
        dict: {is_valid, volume_ok, consecutive_ok, info}
    """
    valid, info = _validate_breakout(df, breakout_direction="up",
                                     volume_ratio=volume_ratio,
                                     close_days=close_confirm_days)
    return {
        "is_valid_breakout": valid,
        "volume_confirmed": info.get("volume_ok", False),
        "close_confirmed": info.get("consecutive_ok", False),
        "info": info,
    }


# ================================================================
#  C. 趋势阶段
# ================================================================

from indicators.trend_quality import (
    detect_top_exhaustion as _detect_top,
    detect_acceleration as _detect_accel,
    classify_pullback_vs_reversal as _classify,
)
from indicators.trend_strength import detect_trend_emergence as _detect_emerge


def exhaustion_signal(df, lookback=60, adx_peak_threshold=35, adx_decline=8,
                      volume_decline_pct=0.20, stagnation_range=0.03):
    """趋势见顶/见底衰竭检测。

    技术原理:
      综合四个维度检测趋势力竭:
      1. 量价背离: 价格创新高但成交量萎缩——"没有放量确认的新高是可疑的"
      2. ADX衰竭: ADX从高位快速回落——"趋势的发动机在熄火"
      3. 放量滞涨: 高位窄幅震荡+放量——主力在出货
      4. HL失败: 跌破前一个显著低点——道氏理论的反转确认

    参数:
        df: DataFrame with high, low, close, volume
        lookback: 回看天数，默认60
        adx_peak_threshold: ADX峰值阈值，需>此值才计为"高位"，默认35
        adx_decline: ADX下降幅度触发衰竭警告，默认8
        volume_decline_pct: 量价背离中的量缩比例，默认0.20(20%)
        stagnation_range: 放量滞涨的价格振幅阈值，默认0.03(3%)

    返回:
        dict: {level: 0-3, signals: list[str], is_exhausted, info}
    """
    level, signals, info = _detect_top(df, lookback=lookback)
    return {
        "level": level,
        "signals": signals,
        "is_exhausted": level >= 2,
        "is_warning": level >= 1,
        "info": info,
    }


def acceleration_signal(df, short_window=5, mid_window=20,
                        accel_ratio_threshold=1.8, vol_ratio_threshold=1.3):
    """加速赶顶/赶底检测。

    技术原理:
      趋势末端往往出现加速——斜率陡增+成交量暴增。
      这是情绪驱动的最后冲刺，利润最丰厚但也最危险。
      加速段出现后应立即收紧止损，准备退出。

    参数:
        df: DataFrame with close, volume
        short_window: 短期窗口，默认5天
        mid_window: 中期窗口，默认20天
        accel_ratio_threshold: 短期涨速/中期涨速的阈值，>此值触发加速信号，默认1.8
        vol_ratio_threshold: 短期量/中期量的阈值，默认1.3

    返回:
        dict: {is_accelerating, direction, accel_ratio, vol_ratio, info}
    """
    is_acc, direction, info = _detect_accel(df, short_window=short_window, mid_window=mid_window)
    return {
        "is_accelerating": is_acc,
        "direction": direction,
        "accel_ratio": info.get("accel_ratio", 1.0),
        "vol_ratio": info.get("vol_ratio", 1.0),
        "warning": "加速中，注意冲顶风险" if direction == "up" else ("加速下跌" if direction == "down" else ""),
        "info": info,
    }


def pullback_or_reversal(df, use_primary_trend=True, low_broken_threshold=0.98,
                         rebound_strength_threshold=0.85):
    """回调 vs 反转判定。

    技术原理:
      这是趋势交易最核心的判断:
      回调 = 长期趋势完好，短期回撤是加仓机会
      反转 = 价格结构破坏（跌破前低），趋势已经改变
      判定依据: 道氏理论低点确认 + 均线状态 + ADX动态

    参数:
        df: DataFrame with high, low, close
        use_primary_trend: 是否假定长期趋势向上，默认True
        low_broken_threshold: HL失败判定阈值，前低*此值被跌破=结构破坏，默认0.98
        rebound_strength_threshold: 反弹力度阈值，反弹<此值=弱势，默认0.85

    返回:
        dict: {classification, is_reversal, is_pullback, info}
    """
    cls, info = _classify(df, primary_up=use_primary_trend)
    return {
        "classification": cls,
        "is_reversal": cls in ("确认反转", "可能反转"),
        "is_pullback": cls == "回调",
        "info": info,
    }


def trend_emergence(df, adx_period=20, adx_threshold=20, lookback=5):
    """趋势初现检测 —— ADX 突破信号。

    技术原理:
      捕捉趋势的"启动瞬间":
      1. ADX 最近 lookback 天内从 <adx_threshold 上穿突破
      2. +DI > -DI（方向确认）
      3. 价格站上 MA(adx_period)
      趋势启动初期是最佳入场时机，风险收益比最高。

    参数:
        df: DataFrame with high, low, close
        adx_period: ADX周期，默认20
        adx_threshold: 上穿阈值，默认20
        lookback: 上穿发生在最近N天内，默认5

    返回:
        dict: {is_emerging, strength: 0-1, info}
    """
    emerged, strength = _detect_emerge(df, adx_period=adx_period,
                                       adx_threshold=adx_threshold, lookback=lookback)
    return {
        "is_emerging": emerged,
        "strength": round(strength, 2),
        "signal": "趋势初现" if emerged else "无",
    }


# ================================================================
#  D. 形态识别
# ================================================================

from indicators.patterns import detect_all_patterns as _detect_all


def chart_patterns(df):
    """综合图表形态识别。

    技术原理:
      经典技术形态是市场心理的可视化呈现。
      反转形态(头肩/双顶底/V顶/圆顶): 趋势可能转向
      持续形态(三角形/楔形): 趋势中的中继整理

    参数:
        df: DataFrame with close

    返回:
        dict: {patterns: {type, confidence, ...}, summary}
    """
    patterns = _detect_all(df)
    found = {k: v for k, v in patterns.items() if v.get("found")}
    return {
        "has_pattern": len(found) > 0,
        "patterns": found,
        "summary": [f"{v['type']}(conf={v.get('confidence', '?')})" for v in found.values()],
    }


# ================================================================
#  E. 相对强度
# ================================================================

from indicators.relative_strength import calc_rs_rank as _rs_rank


def relative_strength(all_returns_dict, periods=(20, 40, 60)):
    """横截面相对强度排名。

    技术原理:
      RS排名衡量标的在所有同类中的相对位置，而非绝对涨跌。
      periods参数支持多周期综合评估（如20/40/60天）。
      RS>0.8 → 处于同类前20%，是真正的强势标的。

    参数:
        all_returns_dict: {code: Series(日收益率)}
        periods: 评估周期元组，默认(20,40,60)覆盖短中长

    返回:
        dict: {code: rs_score(0-1)}
    """
    return _rs_rank(all_returns_dict, periods=list(periods))


# ================================================================
#  F. 市场环境
# ================================================================

from indicators.market_breadth import market_breadth_score as _breadth_score
from indicators.bollinger import bollinger_signal as _bb_signal


def market_environment(dm):
    """市场整体环境评估。

    技术原理:
      综合三个维度:
      1. 市场宽度: 涨跌家数比(参与广度)——广度不足的上涨不可持续
      2. 布林带: 波动率状态——收缩预示突破，扩张确认方向
      3. 多指数确认: 多个指数趋势是否一致

    参数:
        dm: DataManager实例

    返回:
        dict: {breadth_score, bollinger_signal, is_healthy}
    """
    breadth = dm.get_market_breadth_history()
    bscore = _breadth_score(breadth) if breadth is not None and len(breadth) >= 5 else 0.5

    idx_df = dm.get_index_daily("000300")
    bb = _bb_signal(idx_df) if idx_df is not None and not idx_df.empty else {"signal": "数据不足"}

    return {
        "breadth_score": round(bscore, 2),
        "breadth_state": "健康" if bscore > 0.6 else ("中性" if bscore > 0.4 else "弱势"),
        "bollinger_signal": bb.get("signal", "?"),
        "is_squeeze": bb.get("is_squeeze", False),
        "is_healthy": bscore > 0.5,
    }


# ================================================================
#  G. 退出管理
# ================================================================

from indicators.exit_signals import chandelier_exit as _ch_exit, atr_trailing_stop as _atr_ts, \
    ma_trailing_stop as _ma_ts


def exit_strategy(df, entry_price=None, chandelier_mult=3.0, atr_period=22,
                  atr_trail_mult=2.0, ma_exit_period=20, ma_below_days=2):
    """综合退出策略 —— 三种止损/止盈方法。

    技术原理:
      1. 吊灯止损(Chandelier Exit): 从N日最高价回撤M×ATR时退出
         → 让利润奔跑，但防止大幅回吐
      2. ATR移动止损: 止损线随价格上涨自动上移，只上不下
         → 保护浮盈，跟随趋势
      3. 均线止盈: 价格连续跌破MA时退出
         → 简单但有效，适合趋势跟踪

    参数:
        df: DataFrame with high, low, close
        entry_price: 入场价格（可选，用于计算盈亏%）
        chandelier_mult: 吊灯止损ATR倍数，默认3.0（越大越宽松）
        atr_period: ATR计算周期，默认22
        atr_trail_mult: 移动止损ATR倍数，默认2.0
        ma_exit_period: 均线止盈周期，默认20
        ma_below_days: 跌破MA后触发止盈所需天数，默认2

    返回:
        dict: {should_exit, reasons[], stop_prices, pnl_pct}
    """
    ch_stop, ch_info = _ch_exit(df, atr_multiple=chandelier_mult, atr_period=atr_period)
    atr_stop, atr_info = _atr_ts(df, atr_multiple=atr_trail_mult, atr_period=atr_period)
    should_ma, _, ma_info = _ma_ts(df, ma_period=ma_exit_period, close_below_days=ma_below_days)

    reasons = []
    close = df["close"].iloc[-1]

    if ch_stop and close < ch_stop:
        reasons.append(f"吊灯止损({ch_stop:.2f})")
    if atr_stop and close < atr_stop:
        reasons.append(f"ATR移动止损({atr_stop:.2f})")
    if should_ma:
        reasons.append(f"均线止盈(跌破MA{ma_exit_period})")

    result = {
        "should_exit": len(reasons) > 0,
        "reasons": reasons,
        "stop_prices": {
            "chandelier": ch_stop,
            "atr_trailing": atr_stop,
            "ma_exit": round(ma_info.get("ma", 0), 2),
        },
        "current": round(close, 2),
    }
    if entry_price:
        result["pnl_pct"] = round((close / entry_price - 1) * 100, 1)
    return result


# ================================================================
#  H. 行业轮动
# ================================================================

from indicators.rotation import detect_rotation as _detect_rot


def sector_rotation(dm, lookback_short=5, lookback_long=20, top_n=10):
    """行业轮动检测。

    技术原理:
      强弱转换 = 短期排名 vs 长期排名的显著差异。
      短期排名突然跃升而长期排名靠后的行业 → 资金正在流入。
      这是A股"板块轮动"特征的最直接量化方式。

    参数:
        dm: DataManager实例
        lookback_short: 短期回看天数，默认5
        lookback_long: 长期回看天数，默认20
        top_n: 输出转换最显著的前N个行业

    返回:
        dict: {strengthening[], weakening[], summary}
    """
    result = _detect_rot(dm, lookback_short=lookback_short,
                         lookback_long=lookback_long, top_n=top_n)
    return {
        "strengthening": result.get("strengthening", []) if isinstance(result, dict) else [],
        "weakening": result.get("weakening", []) if isinstance(result, dict) else [],
        "summary": f"{len(result.get('strengthening', []))}走强 / "
                   f"{len(result.get('weakening', []))}走弱" if isinstance(result, dict) else "无数据",
    }


# ================================================================
#  I. 量价分析
# ================================================================

from indicators.volume_analysis import check_volume_healthy as _vol_healthy, volume_trend_score as _vol_trend


def volume_analysis(df, window=20, healthy_ratio=1.1):
    """量价配合分析。

    技术原理:
      健康的上升趋势 = 上涨放量(需求推动) + 下跌缩量(卖压减轻)。
      量价背离(价涨量缩)是趋势衰竭的早期信号。
      "量比价先行"——成交量变化通常领先于价格变化。

    参数:
        df: DataFrame with close, volume
        window: 统计窗口，默认20天
        healthy_ratio: 上涨日量/下跌日量的健康阈值，默认1.1

    返回:
        dict: {is_healthy, up_down_vol_ratio, vol_trend_score}
    """
    healthy = _vol_healthy(df, window=window)
    vt_score = _vol_trend(df)

    return {
        "is_healthy": healthy,
        "vol_trend_score": vt_score,
        "state": "量价健康" if healthy else "量价异常(警惕)",
    }


# ================================================================
#  综合复盘 —— 一键跑全部策略
# ================================================================

def full_review(df, dm=None, symbol="", name="", is_index=False):
    """对单个标的运行全部策略，输出完整复盘结果。

    参数:
        df: 标的日线 DataFrame
        dm: DataManager（行业轮动/市场环境需要）
        symbol: 标的代码
        name: 标的名称
        is_index: 是否是指数

    返回:
        dict: 包含所有策略结果的完整复盘报告
    """
    if len(df) < 120:
        return {"error": "数据不足(需≥120天)", "symbol": symbol}

    review = {
        "symbol": symbol,
        "name": name or symbol,
        "date": str(df.index[-1])[:10],
        "close": round(df["close"].iloc[-1], 2),
        "data_days": len(df),
    }

    # A. 趋势识别
    review["adx"] = adx_trend_strength(df)
    review["ma_alignment"] = ma_alignment(df)
    review["three_timeframe"] = trend_three_timeframe(df)
    review["price_structure"] = price_structure(df)

    # B. 趋势质量
    review["oscillation"] = oscillation_filter(df)
    review["breakout"] = breakout_quality(df)

    # C. 趋势阶段
    review["exhaustion"] = exhaustion_signal(df)
    review["acceleration"] = acceleration_signal(df)
    review["pullback_vs_reversal"] = pullback_or_reversal(df)
    review["emergence"] = trend_emergence(df)

    # D. 形态
    review["patterns"] = chart_patterns(df)

    # E. 量价
    review["volume"] = volume_analysis(df)

    # F. 退出
    review["exit"] = exit_strategy(df)

    # G. 行业轮动(需要dm)
    if dm:
        review["market_env"] = market_environment(dm)

    # 综合评分
    scores = []
    if review["three_timeframe"]["total_score"]:
        scores.append(("三层趋势", review["three_timeframe"]["total_score"] * 100))
    if review["adx"]["is_trending"]:
        scores.append(("ADX趋势", min(review["adx"]["adx"] / 40 * 100, 100)))
    if review["ma_alignment"]["long_term_up"]:
        scores.append(("均线多头", 100))
    if review["volume"]["is_healthy"]:
        scores.append(("量价健康", 100))
    if review["emergence"]["is_emerging"]:
        scores.append(("趋势初现", 90))
    if review["exhaustion"]["is_exhausted"]:
        scores.append(("趋势衰竭", -50))
    if review["oscillation"]["should_avoid_trend_strategy"]:
        scores.append(("震荡规避", -100))

    review["composite_score"] = round(sum(s[1] for s in scores) / max(len(scores), 1), 1)
    review["recommendation"] = (
        "强烈推荐" if review["composite_score"] > 70 else
        "可以关注" if review["composite_score"] > 50 else
        "观望" if review["composite_score"] > 30 else
        "回避"
    )

    return review
