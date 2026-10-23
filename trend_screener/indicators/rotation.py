"""
行业轮动信号检测

检测资金在行业板块之间轮动的信号。
"""

import pandas as pd
import numpy as np


def detect_rotation(dm, lookback_short=5, lookback_long=20, top_n=10):
    """检测行业强弱转换信号。

    逻辑:
      强弱转换 = 短期排名 vs 长期排名的显著差异
      例: 某行业长期排名垫底，但近5日涨幅跃升至前10 → 资金正在流入

    参数:
        dm: DataManager 实例
        lookback_short: 短期回看天数
        lookback_long: 长期回看天数
        top_n: 取前N个转换信号

    返回:
        list[dict]: 按转换强度排序的行业列表
    """
    boards = dm.get_industry_boards()
    if not boards:
        return []

    short_rets = {}
    long_rets = {}

    for b in boards:
        code = b["code"]
        df = dm.get_industry_daily(code)
        if df is None or len(df) < lookback_long + 5:
            continue

        close = df["close"]
        if len(close) >= lookback_short:
            sr = close.iloc[-1] / close.iloc[-lookback_short] - 1
        else:
            sr = 0
        if len(close) >= lookback_long:
            lr = close.iloc[-1] / close.iloc[-lookback_long] - 1
        else:
            lr = 0

        short_rets[code] = sr
        long_rets[code] = lr

    if not short_rets:
        return []

    # 排名
    short_rank = pd.Series(short_rets).rank(pct=True)
    long_rank = pd.Series(long_rets).rank(pct=True)

    # 转换信号 = 短期排名 - 长期排名（正值=变强，负值=变弱）
    shift = (short_rank - long_rank).sort_values(ascending=False)

    names = {b["code"]: b["name"] for b in boards}
    results = []
    for code, s in shift.head(top_n * 2).items():  # 取2倍以包含变强和变弱
        results.append({
            "code": code,
            "name": names.get(code, code),
            "shift_strength": round(s, 3),
            "short_ret": round(short_rets.get(code, 0) * 100, 2),
            "long_ret": round(long_rets.get(code, 0) * 100, 2),
            "short_rank": round(short_rank[code] * 100, 0),
            "long_rank": round(long_rank[code] * 100, 0),
        })

    # 分类：变强 / 变弱
    strengthening = [r for r in results if r["shift_strength"] > 0.15]
    weakening = [r for r in results if r["shift_strength"] < -0.15]

    strengthening.sort(key=lambda x: x["shift_strength"], reverse=True)
    weakening.sort(key=lambda x: x["shift_strength"])

    return {
        "strengthening": strengthening[:top_n],   # 正在走强的行业
        "weakening": weakening[:top_n],            # 正在走弱的行业
        "all": results,
    }


def detect_new_leader(dm, previous_leaders=None, top_n=5):
    """检测新龙头行业的出现。

    如果前一期不在 Top N 中的行业本期进入 Top N，标记为新龙头。

    返回:
        list[dict]: 新晋龙头行业
    """
    if previous_leaders is None:
        return []

    from filters.industry_filter import IndustryFilter
    inf = IndustryFilter(dm)
    current = inf.filter(top_n=top_n)
    current_codes = {c["code"] for c in current}
    prev_codes = {p["code"] for p in previous_leaders}

    newcomers = current_codes - prev_codes
    return [c for c in current if c["code"] in newcomers]
