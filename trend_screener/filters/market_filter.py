"""
第一层：大盘趋势过滤器

用多指标评分卡对大盘指数做三时间尺度评估，
输出市场环境等级和是否适合做趋势交易的建议。
"""

import pandas as pd
from datetime import datetime

from config import (
    MARKET_INDICES, PRIMARY_INDEX, MARKET_SCORECARD, SCORE_COLORS,
)
from indicators.multi_timeframe import evaluate_trend
from indicators.market_breadth import market_breadth_score
from indicators.volume_analysis import check_volume_healthy
from data.index_data import get_primary_index, get_all_market_indices


class MarketFilter:
    """大盘趋势评分卡。"""

    def __init__(self, dm):
        self.dm = dm

    def evaluate(self):
        """执行完整的大盘趋势评估。

        返回:
            dict: 与 evaluate_report 输出格式一致
        """
        # 更新当日市场宽度
        try:
            self.dm.update_market_breadth()
        except Exception:
            pass  # 非致命

        # 1. 沪深300 三时间尺度趋势
        hs300 = get_primary_index(self.dm)
        if hs300 is None or hs300.empty:
            return self._empty("沪深300 数据不可用")

        trend = evaluate_trend(hs300)

        # 2. 市场宽度（涨跌家数）
        breadth = self.dm.get_market_breadth_history()
        breadth_score = (
            market_breadth_score(breadth) if breadth is not None and len(breadth) >= 5
            else 0.5
        )

        # 3. 量价配合
        vol_healthy = check_volume_healthy(hs300)

        # 4. 多指数交叉确认
        multi_ok = check_multiple_indices(self.dm)

        # ===== 加权评分 =====
        weights = MARKET_SCORECARD
        detail = {
            "三时间尺度趋势": (trend["total_score"], weights["trend_alignment"]),
            "ADX趋势强度": (
                0.8 if trend["prim_up"] and trend["sec_up"] else
                0.5 if trend["prim_up"] else 0.3,
                weights["adx_strength"],
            ),
            "市场宽度": (breadth_score, weights["market_breadth"]),
            "量价配合": (1.0 if vol_healthy else 0.0, weights["volume_health"]),
            "均线斜率确认": (
                self._slope_ok(hs300), weights["slope_confirm"],
            ),
            "多指数确认": (1.0 if multi_ok else 0.0, weights["multi_index"]),
        }

        total_score = sum(v * w for v, w in detail.values())
        total_score = round(total_score, 2)

        # 等级划分
        grade = self._grade(total_score)

        # 建议
        recommendations = {
            "A": "强趋势市，全力做多，正常仓位",
            "B": "趋势市，做多为主，适度仓位",
            "C": "弱趋势，半仓操作或观望",
            "D": "不适合做趋势交易，暂停参与",
        }

        return {
            "score": total_score,
            "grade": grade,
            "trend": trend,
            "breadth_score": round(breadth_score, 2),
            "vol_healthy": vol_healthy,
            "multi_index_ok": multi_ok,
            "details": {k: (v, round(w, 2)) for k, (v, w) in detail.items()},
            "recommendation": recommendations[grade],
            "timestamp": datetime.now().isoformat(),
        }

    def _slope_ok(self, df):
        """检查沪深300的MA20斜率是否健康。"""
        from indicators.trend_strength import ma_slope
        s = ma_slope(df, 20, 10)
        return 1.0 if s > 0.001 else 0.5 if s > -0.001 else 0.0

    def _grade(self, score):
        """根据总分确定等级。"""
        if score >= 0.70:
            return "A"
        elif score >= 0.50:
            return "B"
        elif score >= 0.30:
            return "C"
        else:
            return "D"

    def _empty(self, reason):
        return {
            "score": 0.0, "grade": "D",
            "trend": None, "breadth_score": 0.0,
            "vol_healthy": False, "multi_index_ok": False,
            "details": {}, "recommendation": reason,
            "timestamp": datetime.now().isoformat(),
        }


# ---- 辅助函数（可独立使用）----

def check_volume_healthy(df, window=20):
    """量价配合检查（公开版）。"""
    from indicators.volume_analysis import check_volume_healthy as _cvh
    return _cvh(df, window)


def check_multiple_indices(dm):
    """多指数趋势一致性检查。

    要求沪深300 + 中证500 + 创业板指中至少2个趋势向上。
    """
    ok_count = 0
    for idx in MARKET_INDICES:
        df = dm.get_index_daily(idx["code"])
        if df is None or len(df) < 60:
            continue
        trend = evaluate_trend(df)
        if trend["prim_up"]:
            ok_count += 1
    return ok_count >= 2


# ---- 便捷入口 ----

def filter_market(dm):
    """快速执行大盘过滤（简化版入口）。"""
    mf = MarketFilter(dm)
    return mf.evaluate()
