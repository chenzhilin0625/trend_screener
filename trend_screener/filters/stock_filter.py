"""
第三层：个股趋势过滤器（v2 —— 成分股限定 + 全量可选）

默认：只扫描 tdxhy.cfg 中有行业分类的股票（~5600只）
full_scan=True：扫描 DB 中全部股票（~9400只）
"""

import pandas as pd
from datetime import datetime

from config import STOCK_FILTER, SECONDARY_TREND
from indicators.multi_timeframe import evaluate_trend
from indicators.price_structure import identify_swing_points, check_trend_structure
from indicators.trend_strength import adx
from indicators.volume_analysis import check_volume_healthy
from indicators.overbought import overbought_score
try:
    from data.tdx_sync import get_all_mapped_stock_codes, get_stock_industry_map, get_board_names
except ImportError:
    get_all_mapped_stock_codes = lambda: []
    get_stock_industry_map = lambda: {}
    get_board_names = lambda: {}


class StockFilter:
    """个股趋势过滤器。"""

    def __init__(self, dm):
        self.dm = dm
        self._industry_map = None  # stock_code → [board_name, ...]

    def _load_industry_map(self):
        """构建 stock_code → 行业标签 映射。

        注意: tdxhy.cfg 的 T-code 和板块名的 880xxx 编码是两个独立体系，
        当前直接展示 T-code 作为行业标识。
        """
        if self._industry_map is not None:
            return self._industry_map
        stock_tcodes = get_stock_industry_map()
        # 也加载 top industries 的名称做关键词匹配
        result = {}
        for code, tcodes in stock_tcodes.items():
            # 直接显示 T-code（如 \"T1001\"）
            result[code] = ", ".join(tcodes[:3])
        self._industry_map = result
        return result

    def filter(self, top_industries, max_stocks=None, benchmark_df=None,
               full_scan=False):
        """在强势行业中筛选趋势结构清晰的个股。

        参数:
            top_industries: IndustryFilter.filter() 的输出
            max_stocks:     最终输出上限
            benchmark_df:   大盘基准日线
            full_scan:      True=全量扫描所有股票; False=只扫描有行业分类的股票

        返回:
            list[dict]: 候选股票列表
        """
        max_stocks = max_stocks or STOCK_FILTER["max_stocks"]
        top_n_industries = STOCK_FILTER["top_industries_to_scan"]
        scan_industries = top_industries[:top_n_industries]

        # 获取待扫描的股票代码
        if full_scan:
            stock_codes = self._get_db_all_codes()
        else:
            stock_codes = self._get_industry_scoped_codes()

        if not stock_codes:
            return []

        print(f"  scan pool: {len(stock_codes)} stocks"
                  f"{' (full)' if full_scan else ''}")

        if benchmark_df is None:
            benchmark_df = self.dm.get_index_daily("000300")

        # 加载行业映射
        ind_map = self._load_industry_map()

        candidates = []
        for code in stock_codes:
            df = self.dm.get_stock_daily(code)
            if df is None or len(df) < STOCK_FILTER["min_data_days"]:
                continue

            checks = self._run_checks(df, benchmark_df)
            passed = sum(1 for k, v in checks.items()
                        if not k.startswith("_") and v is True)
            if passed >= STOCK_FILTER["min_passed_checks"]:
                adx_val = checks.get("_adx_val", 0)
                trend = checks.get("_trend", {})
                name = self.dm.get_stock_name(code)
                ob = checks.get("_ob", {})
                # 行业归属（T-code → 板块名映射暂无本地文件，显示T-code占位）
                industries = ind_map.get(code, ["-"])
                ind_str = industries[0] if industries else "-"
                candidates.append({
                    "code": code,
                    "name": name,
                    "industry": ind_str,
                    "checks": {k: v for k, v in checks.items()
                              if not k.startswith("_") and k != "_trend"},
                    "passed": passed,
                    "adx": round(adx_val, 1),
                    "score": passed + min(adx_val / 10, 3.0),
                    "long_up": trend.get("prim_up", False),
                    "mid_up": trend.get("sec_up", False),
                    "short_up": trend.get("min_up", False),
                    "trend_state": trend.get("state", ""),
                    "ob_score": ob.get("score", 0),
                    "ob_level": ob.get("level", "正常"),
                    "ob_warnings": ob.get("warnings", []),
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:max_stocks]

    def _get_industry_scoped_codes(self):
        """获取有行业分类映射的股票代码（默认扫描范围，约5600只）。"""
        codes = get_all_mapped_stock_codes()
        # 只保留沪深主板+创业板+科创板
        return [c for c in codes if c[:2] in ("60", "00", "30", "68")]

    def _get_db_all_codes(self):
        """全量：DB 中所有股票（full_scan 模式，约9400只）。"""
        cur = self.dm._conn.cursor()
        cur.execute("SELECT DISTINCT ts_code FROM stock_daily ORDER BY ts_code")
        codes = [r[0] for r in cur.fetchall()]
        return [c for c in codes if c[:2] in ("60", "00", "30", "68")]

    def _run_checks(self, df, benchmark_df):
        """7 项趋势检查。"""
        checks = {}
        close = df["close"]

        # 1. 三时间尺度趋势
        trend = evaluate_trend(df)
        checks["_trend"] = trend
        checks["三尺度趋势"] = trend["total_score"] >= 0.45
        checks["_total_score"] = trend["total_score"]

        # 2. HH/HL 价格结构
        highs, lows = identify_swing_points(df, threshold=SECONDARY_TREND["swing_threshold"])
        structure_ok, quality = check_trend_structure(highs, lows, min_swings=2)
        checks["HH/HL结构"] = structure_ok
        checks["_structure_quality"] = quality

        # 3. 均线多头排列
        ema10 = close.ewm(span=10).mean().iloc[-1]
        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema60 = close.ewm(span=60).mean().iloc[-1]
        checks["均线排列"] = (pd.notna(ema10) and pd.notna(ema20) and pd.notna(ema60)
                            and ema10 > ema20 > ema60)

        # 4. ADX 趋势强度
        adx_val, plus_di, minus_di = adx(df, period=20)
        checks["ADX强度"] = adx_val > STOCK_FILTER["min_adx"] and plus_di > minus_di
        checks["_adx_val"] = adx_val

        # 5. 站上 MA60
        checks["站上MA60"] = (pd.notna(ema60) and close.iloc[-1] > ema60)

        # 6. 量价配合
        checks["量价健康"] = check_volume_healthy(df)

        # 7. 相对强度 vs 大盘
        rs_vs = 1.0
        if benchmark_df is not None and not benchmark_df.empty:
            sr = close.iloc[-1] / close.iloc[-60] - 1 if len(close) >= 60 else 0
            br = (benchmark_df["close"].iloc[-1] / benchmark_df["close"].iloc[-60] - 1
                  if len(benchmark_df) >= 60 else 0)
            rs_vs = sr / br if br != 0 and not pd.isna(br) else 1.0
        checks["相对强度>1.0"] = rs_vs > 1.0
        checks["_rs_vs_index"] = round(rs_vs, 2)

        # 8. 过热检测（扣分项，不算在 passed 里）
        ob = overbought_score(df)
        checks["_ob"] = ob

        return checks


def filter_stocks(dm, top_industries, max_stocks=None, full_scan=False):
    sf = StockFilter(dm)
    return sf.filter(top_industries, max_stocks=max_stocks, full_scan=full_scan)
