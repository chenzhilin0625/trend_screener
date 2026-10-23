# -*- coding: utf-8 -*-
"""终端输出 —— 表格化趋势筛选报告"""

import os
from datetime import datetime

if os.name == "nt":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

# ---- ANSI 颜色 ----
C = {
    "dg": "\033[1;32m", "gn": "\033[0;32m", "lg": "\033[0;92m",
    "yl": "\033[0;33m", "or": "\033[0;91m", "rd": "\033[1;31m",
    "cy": "\033[0;36m", "gy": "\033[0;90m", "b": "\033[1m",
    "xx": "\033[0m",
}


def c(text, color):
    codes = [C[k] for k in color.split() if k in C]
    return "".join(codes) + str(text) + C["xx"] if codes else str(text)


def _c_for(v):
    if v >= 0.85: return "dg"
    if v >= 0.70: return "gn"
    if v >= 0.55: return "lg"
    if v >= 0.40: return "yl"
    if v >= 0.25: return "or"
    return "rd"


def _arrow(up):
    return c("UP", "dg") if up else c("DN", "rd")


def _ob_color(level):
    if level in ("过热", "严重过热"): return "or"
    if level == "偏高": return "yl"
    return "dg"


# ---- 辅助函数 ----

def _hd(*cols):
    return "  ".join(c(h, "b") for h in cols)


def _sep(width):
    print(c("  " + "-" * width, "gy"))


# ================================================================
#  行业表格
# ================================================================

def print_industry_table(industries, top_n=15):
    """行业表格：每行一个行业，列为各技术指标。"""
    print()
    print(c("=" * 120, "cy"))
    print(c("  Industry Trend Matrix", "b"))
    print(c("=" * 120, "cy"))

    if not industries:
        print(c("  (no data)", "gy"))
        return

    # 表头
    hdr = (
        f"{'#':>3}  {'Industry':<14s}  {'Score':>6s}  "
        f"{'L':>3s}{'M':>3s}{'S':>3s}  "
        f"{'RS':>6s}  {'ADX':>5s}  {'%B':>5s}  {'RSI':>5s}  "
        f"{'MA20%':>6s}  {'ROC10%':>7s}  {'OB':>6s}  "
        f"{'State':<10s}  {'Flags':s}"
    )
    print(c(hdr, "b"))
    _sep(118)

    for i, ind in enumerate(industries[:top_n], 1):
        s = ind["total_score"]
        ob = ind.get("ob_score", 0)
        ob_lvl = ind.get("ob_level", "?")
        # ADX 估算（从 trend 数据反推或显示趋势分数）
        adx_disp = f"{ind['prim_score']:.0f}/{ind['sec_score']:.0f}"
        # 标签
        flags = " ".join(ind.get("labels", []))

        # OB 信息
        ob_details = ind.get("ob_details", {})
        bb_str = f"{ob_details.get('%B', '-'):.2f}" if isinstance(ob_details.get("%B"), float) else "-"
        rsi_disp = f"{ob_details.get('RSI(14)', '-'):.0f}" if isinstance(ob_details.get("RSI(14)"), (int, float)) else "-"
        ma20d = ob_details.get("MA20偏离", "-")
        roc_disp = ob_details.get("10日涨速", "-")

        color = _c_for(s)
        score_cell = c("{:.3f}".format(s), color)
        rs_str = "{:.3f}".format(ind["rs_score"])
        rs_cell = c(rs_str, _c_for(ind["rs_score"]))
        ob_cell = c(ob_lvl, _ob_color(ob_lvl))
        state_str = ind["trend_state"]

        line = (
            "  {:>3}  {:<14s}  {:>21s}  "
            "{:>6s}{:>6s}{:>6s}  "
            "{:>10s}  "
            "{:>5s}  {:>5s}  {:>5s}  "
            "{:>6s}  {:>7s}  "
            "{:>12s}  "
            "{:<10s}  "
        ).format(
            i, ind["name"], score_cell,
            _arrow(ind["prim_up"]), _arrow(ind["sec_up"]), _arrow(ind["min_up"]),
            rs_cell,
            adx_disp, bb_str, rsi_disp,
            str(ma20d), str(roc_disp),
            ob_cell,
            state_str,
        )
        if flags:
            line += c(flags, "gy")
        print(line)

    # 汇总
    all_up = sum(1 for i in industries[:top_n]
                 if i["prim_up"] and i["sec_up"] and i["min_up"])
    pb_count = sum(1 for i in industries[:top_n] if i.get("is_pullback"))
    em_count = sum(1 for i in industries[:top_n] if i.get("is_emergence"))
    ob_count = sum(1 for i in industries[:top_n]
                   if i.get("ob_level") in ("过热", "严重过热"))
    rg_count = sum(1 for i in industries[:top_n] if i.get("is_ranging"))
    print()
    print(c(f"  Resonance(3/3): {all_up} | Pullback: {pb_count} | "
            f"Emergence: {em_count} | Overbought: {ob_count} | "
            f"Ranging: {rg_count}", "gy"))


# ================================================================
#  个股表格
# ================================================================

def print_stock_table(stocks, top_n=20):
    """个股表格：每行一只股票，7项检查独立列。"""
    print()
    print(c("=" * 130, "cy"))
    print(c("  Stock Trend Candidates", "b"))
    print(c("=" * 130, "cy"))

    if not stocks:
        print(c("  (no candidates)", "gy"))
        return

    # 表头
    hdr = (
        f"{'#':>3}  {'Code':<10s} {'Name':<10s} {'Industry':<18s} "
        f"{'Sc':>4s}  {'P':>2s}  "
        f"{'L':>3s}{'M':>3s}{'S':>3s}  "
        f"{'ADX':>5s}  {'3TF':>3s} {'HH':>3s} {'EMA':>3s} {'ADXc':>3s} {'60':>3s} {'Vol':>3s} {'RS':>3s}  "
        f"{'OB':>6s}  {'State':s}"
    )
    print(c(hdr, "b"))
    _sep(148)

    for i, s in enumerate(stocks[:top_n], 1):
        chk = s.get("checks", {})
        ob_lvl = s.get("ob_level", "?")
        ind_str = s.get("industry", "")

        sc_cell = c("{:.1f}".format(s['score']), _c_for(s['score'] / 7))
        ob_cell = c(ob_lvl, _ob_color(ob_lvl))
        st_cell = s.get("trend_state", "")

        line = (
            "  {:>3}  {:<10s} {:<10s} {:<18s} "
            "{:>8s}  "
            "{:>2d}  "
            "{:>6s}{:>6s}{:>6s}  "
            "{:>5.1f}  "
            "{:>3s} {:>3s} {:>3s} {:>3s} {:>3s} {:>3s} {:>3s}  "
            "{:>12s}  "
            "{}"
        ).format(
            i, s["code"], s["name"], ind_str[:18],
            sc_cell,
            s["passed"],
            _arrow(s["long_up"]), _arrow(s["mid_up"]), _arrow(s["short_up"]),
            s["adx"],
            _yn(chk.get("三尺度趋势", False)),
            _yn(chk.get("HH/HL结构", False)),
            _yn(chk.get("均线排列", False)),
            _yn(chk.get("ADX强度", False)),
            _yn(chk.get("站上MA60", False)),
            _yn(chk.get("量价健康", False)),
            _yn(chk.get("相对强度>1.0", False)),
            ob_cell,
            st_cell,
        )
        print(line)

    # 汇总
    all_up = sum(1 for s in stocks[:top_n]
                 if s["long_up"] and s["mid_up"] and s["short_up"])
    ob_count = sum(1 for s in stocks[:top_n]
                   if s.get("ob_level") in ("过热", "严重过热"))
    avg_adx = sum(s["adx"] for s in stocks[:top_n]) / max(len(stocks[:top_n]), 1)
    print()
    print(c(f"  Resonance(3/3): {all_up} | Overbought: {ob_count} | "
            f"Avg ADX: {avg_adx:.1f}", "gy"))


def _yn(val):
    if val is True:
        return c(" Y", "dg")
    elif val is False:
        return c(" N", "rd")
    return " -"


# ================================================================
#  大盘报告
# ================================================================

def print_market_report(market_result):
    print()
    print(c("=" * 80, "cy"))
    print(c("  Market Assessment", "b"))
    print(c("=" * 80, "cy"))

    if market_result is None or market_result.get("score", 0) == 0:
        print(c("  X Market data unavailable", "rd"))
        return

    score = market_result["score"]
    grade = market_result["grade"]
    gc = {"A": "dg", "B": "gn", "C": "yl", "D": "rd"}.get(grade, "gn")

    print(f"  Score: {c(f'{score:.2f}', gc)}  "
          f"Grade: {c(grade, gc + ' b')}")
    print(f"  Advice: {c(market_result['recommendation'], gc)}")

    trend = market_result.get("trend")
    if trend:
        p = _arrow(trend["prim_up"])
        s = _arrow(trend["sec_up"])
        m = _arrow(trend["min_up"])
        print(f"  Trend: Long {p} Mid {s} Short {m}  "
              f"-> {c(trend['state'], gc)}")
        print(f"  Scores: Long {trend['primary_score']:.1f}/4  "
              f"Mid {trend['secondary_score']:.1f}/4  "
              f"Short {trend['minor_score']:.1f}/3  "
              f"Composite {trend['total_score']:.3f}")

    print()
    br = market_result.get("breadth_score", 0)
    vol = market_result.get("vol_healthy", False)
    mu = market_result.get("multi_index_ok", False)
    print(f"  Breadth: {c(f'{br:.2f}', _c_for(br))}  "
          f"Volume: {c('OK' if vol else 'NO', 'dg' if vol else 'rd')}  "
          f"Multi-Index: {c('OK' if mu else 'NO', 'dg' if mu else 'rd')}")

    print()
    print(c("  Scorecard:", "gy"))
    for name, (val, weight) in market_result.get("details", {}).items():
        bar = "#" * int(val * 20)
        print(f"    {name:<14} {bar:<22} {val:.2f} x{weight:.0%}")


def print_summary_footer(market, industries, stocks):
    print()
    print(c("=" * 80, "cy"))
    grade = market.get("grade", "D") if market else "D"
    print(f"  Market: {c(grade, _c_for(market['score'] if market else 0))}"
          f"  |  Industries: {len(industries)}"
          f"  |  Candidates: {len(stocks)}  |  "
          f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(c("=" * 80, "cy"))


# ---- 便捷入口 ----

def print_report(market_result, top_industries, stock_candidates):
    print_market_report(market_result)
    print_industry_table(top_industries)
    print_stock_table(stock_candidates)
    print_summary_footer(market_result, top_industries, stock_candidates)
