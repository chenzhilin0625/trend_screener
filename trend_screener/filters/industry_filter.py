"""
第二层：行业趋势过滤器（增强版）

新增功能：
  - 回调识别：长期向上 + 短期回调 → 标记"回调买点"
  - 趋势初现：ADX 刚上穿 → 标记"趋势初现"
"""

from datetime import datetime

from data.industry_data import (
    get_all_industry_data, map_to_sw_category, get_industry_returns,
)
from indicators.multi_timeframe import evaluate_trend
from indicators.relative_strength import calc_rs_rank
from indicators.trend_strength import detect_trend_emergence, detect_pullback
from indicators.overbought import overbought_score
from indicators.trend_quality import is_ranging
from config import (
    PRIMARY_TREND, SECONDARY_TREND, PULLBACK, TREND_EMERGENCE,
)


class IndustryFilter:
    """行业趋势过滤器。"""

    def __init__(self, dm):
        self.dm = dm

    def filter(self, top_n=20, market_grade=None):
        """对所有行业板块打分排名，同时检测回调和趋势初现。

        返回:
            list[dict]: 按综合得分降序排列的行业列表
        """
        industry_data = get_all_industry_data(self.dm)
        if not industry_data:
            return []

        # 构建收益率映射
        returns_map = {}
        for code, info in industry_data.items():
            rets = info["df"]["close"].pct_change().dropna()
            if len(rets) >= 60:
                returns_map[code] = rets

        rs_scores = calc_rs_rank(returns_map, periods=SECONDARY_TREND["rs_periods"])

        results = []
        for code, info in industry_data.items():
            df = info["df"]
            name = info["name"]

            if len(df) < 120:
                continue

            trend = evaluate_trend(df)
            rs = rs_scores.get(code, 0.0)
            total = self._composite_score(trend, rs)
            sw = map_to_sw_category(name)

            # ---- 回调检测 ----
            is_pb, pb_depth, pb_info = detect_pullback(
                df, primary_up=trend["prim_up"]
            )

            # ---- 趋势初现检测 ----
            emerged, em_strength = detect_trend_emergence(
                df,
                adx_period=TREND_EMERGENCE["adx_period"],
                adx_threshold=TREND_EMERGENCE["adx_threshold"],
                lookback=TREND_EMERGENCE["lookback"],
            )

            # ---- 震荡过滤 ----
            ranging, ranging_info = is_ranging(df)
            if ranging:
                total -= 0.25  # 震荡市扣分

            # ---- 过热检测 ----
            ob = overbought_score(df)

            # 标签
            labels = []
            if emerged:
                labels.append("趋势初现")
            if is_pb:
                labels.append(f"回调-{pb_info.get('drawdown_pct', 0)}%")
            if ranging:
                labels.append("震荡")
            if ob["level"] in ("过热", "严重过热"):
                labels.append(ob["level"])

            results.append({
                "code": code,
                "name": name,
                "sw_label": sw,
                "total_score": round(total, 3),
                "rs_score": round(rs, 3),
                "prim_score": trend["primary_score"],
                "sec_score": trend["secondary_score"],
                "min_score": trend["minor_score"],
                "trend_state": trend["state"],
                "action": trend["action"],
                "prim_up": trend["prim_up"],
                "sec_up": trend["sec_up"],
                "min_up": trend["min_up"],
                # 新增
                "is_pullback": is_pb,
                "pullback_depth": pb_depth,
                "pullback_info": pb_info,
                "is_emergence": emerged,
                "emergence_strength": em_strength,
                "is_ranging": ranging,
                "ranging_info": ranging_info,
                "ob_score": ob["score"],
                "ob_level": ob["level"],
                "ob_warnings": ob["warnings"],
                "ob_details": ob.get("details", {}),
                "labels": labels,
            })

        results.sort(key=lambda x: x["total_score"], reverse=True)

        if market_grade == "C":
            results = [r for r in results if r["total_score"] >= 0.4]

        return results[:top_n]

    def _composite_score(self, trend, rs):
        trend_part = trend["total_score"] * 0.60
        rs_part = rs * 0.40
        return trend_part + rs_part

    def get_pullback_industries(self, all_results, max_count=None):
        """从全部行业结果中筛选出处于回调的行业（长期向上+短期回调）。

        返回:
            list[dict]: 按回调幅度排序
        """
        max_count = max_count or PULLBACK["max_pullback_count"]
        pullbacks = [r for r in all_results if r["is_pullback"]]
        # 按 total_score 排序（趋势强+回调 = 好买点）
        pullbacks.sort(key=lambda x: x["total_score"], reverse=True)
        return pullbacks[:max_count]

    def get_emergence_industries(self, all_results, max_count=None):
        """筛选趋势初现的行业（ADX 刚上穿）。

        返回:
            list[dict]: 按 emergence_strength 排序
        """
        max_count = max_count or TREND_EMERGENCE["max_emergence_count"]
        emerged = [r for r in all_results if r["is_emergence"]]
        emerged.sort(key=lambda x: x["emergence_strength"], reverse=True)
        return emerged[:max_count]

    def get_sw_summary(self, results):
        summary = {}
        for r in results:
            sw = r["sw_label"]
            summary[sw] = summary.get(sw, 0) + 1
        return summary

    def flag_standalone(self, results, threshold=1):
        sw_counts = {}
        for r in results:
            sw = r["sw_label"]
            sw_counts[sw] = sw_counts.get(sw, []) + [r["code"]]
        standalone = []
        for sw, codes in sw_counts.items():
            if len(codes) <= threshold:
                standalone.extend(codes)
        return standalone


def filter_industries(dm, top_n=20, market_grade=None):
    inf = IndustryFilter(dm)
    return inf.filter(top_n=top_n, market_grade=market_grade)
