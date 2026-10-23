"""
趋势筛选器 —— 主入口（纯本地版 v2.2）

用法:
    python main.py                    日常使用：成分股内筛选
    python main.py --full-scan        全量扫描所有股票（慢）
    python main.py --market-only      仅评估大盘趋势
    python main.py --report           生成 Markdown 报告
    python main.py --verbose          详细日志
"""

import sys
import time
from datetime import datetime

from data.manager import DataManager
from filters.market_filter import MarketFilter
from filters.industry_filter import IndustryFilter
from filters.stock_filter import StockFilter
from output.console import print_report, print_market_report
from output.report import generate_report
from utils.logger import Logger


def main():
    args = set(sys.argv[1:])
    verbose = "--verbose" in args
    market_only = "--market-only" in args
    full_scan = "--full-scan" in args

    t_start = time.time()
    log = Logger()

    log.info("=" * 60)
    log.info("  趋势筛选器 v2.2 (本地版)")
    scan_mode = "全量" if full_scan else "成分股"
    log.info(f"  扫描模式: {scan_mode}")
    log.info("=" * 60)

    # ---- 数据层 ----
    dm = DataManager()

    # ---- 市场宽度 ----
    dm.update_market_breadth()
    breadth = dm.get_market_breadth_history()

    # ================================================================
    #  Layer 1: 大盘趋势 —— 长中短期分维度
    # ================================================================
    log.info("-" * 60)
    log.info("[Layer 1/3] 大盘趋势 —— 长/中/短期")
    log.info("-" * 60)

    mf = MarketFilter(dm)
    market_result = mf.evaluate()
    mkt_trend = market_result.get("trend", {})

    # 始终输出三层趋势
    if mkt_trend:
        log.info(f"  长期(周线): score={mkt_trend['primary_score']:.1f}/4  "
                 f"{'↑ 上升' if mkt_trend['prim_up'] else '↓ 下降'}")
        log.info(f"  中期(日线): score={mkt_trend['secondary_score']:.1f}/4  "
                 f"{'↑ 上升' if mkt_trend['sec_up'] else '↓ 下降'}")
        log.info(f"  短期(日线): score={mkt_trend['minor_score']:.1f}/3  "
                 f"{'↑ 上升' if mkt_trend['min_up'] else '↓ 下降'}")
        log.info(f"  综合状态: {mkt_trend['state']} | {mkt_trend['action']} | "
                 f"评级: {market_result['grade']}级 ({market_result['score']:.2f})")

    if verbose and not breadth.empty:
        latest = breadth.iloc[-1]
        log.info(f"  市场宽度: 涨{int(latest['up_count'])}/"
                 f"跌{int(latest['down_count'])}/"
                 f"共{int(latest['total_count'])}")

    if market_only:
        print_market_report(market_result)
        dm.close(); log.close(); return

    if market_result["grade"] == "D":
        log.info("  [终止] 大盘 D 级，不适合做多")
        print_report(market_result, [], [])
        dm.close(); log.close(); return

    # ================================================================
    #  Layer 2: 行业趋势 —— 长中短期分维度
    # ================================================================
    log.info("-" * 60)
    log.info("[Layer 2/3] 行业趋势 —— 长/中/短期")
    log.info("-" * 60)

    inf = IndustryFilter(dm)
    top_industries = inf.filter(market_grade=market_result["grade"])

    # 分维度统计
    ind_long_up = [i for i in top_industries if i["prim_up"]]
    ind_mid_up = [i for i in top_industries if i["sec_up"]]
    ind_short_up = [i for i in top_industries if i["min_up"]]
    ind_all_up = [i for i in top_industries
                  if i["prim_up"] and i["sec_up"] and i["min_up"]]

    log.info(f"  共分析 {len(dm.get_industry_boards())} 个行业板块")
    log.info(f"  入选 {len(top_industries)} 个强势行业")
    log.info(f"  其中:")
    log.info(f"    长期上升: {len(ind_long_up)} 个")
    log.info(f"    中期上升: {len(ind_mid_up)} 个")
    log.info(f"    短期上升: {len(ind_short_up)} 个")
    log.info(f"    三层共振(主升浪): {len(ind_all_up)} 个")

    if verbose and top_industries:
        log.info(f"\n  Top 10 强势行业:")
        for i, ind in enumerate(top_industries[:10], 1):
            p = "↑" if ind["prim_up"] else "↓"
            s = "↑" if ind["sec_up"] else "↓"
            m = "↑" if ind["min_up"] else "↓"
            log.info(f"  {i:2d}. {ind['name']:<12s} "
                     f"score={ind['total_score']:.3f} "
                     f"长{p}中{s}短{m} | {ind['trend_state']}")

    # 回调行业
    pullbacks = inf.get_pullback_industries(top_industries, max_count=10)
    if verbose and pullbacks:
        log.info(f"\n  [回调买点] ({len(pullbacks)} 个):")
        for pb in pullbacks[:5]:
            info = pb.get("pullback_info", {})
            log.info(f"    {pb['name']}  回调{info.get('drawdown_pct',0)}%  "
                     f"score={pb['total_score']:.2f}")

    if not top_industries:
        log.info("  [终止] 无强势行业")
        print_report(market_result, [], [])
        dm.close(); log.close(); return

    # ================================================================
    #  Layer 3: 个股趋势 —— 成分股内 + 长中短期分维度
    # ================================================================
    log.info("-" * 60)
    log.info("[Layer 3/3] 个股趋势 —— 长/中/短期")
    log.info("-" * 60)

    sf = StockFilter(dm)
    benchmark_df = dm.get_index_daily("000300")
    stock_candidates = sf.filter(top_industries, benchmark_df=benchmark_df,
                                 full_scan=full_scan)

    # 分维度统计个股
    stk_long_up = [s for s in stock_candidates if s.get("long_up")]
    stk_mid_up = [s for s in stock_candidates if s.get("mid_up")]
    stk_short_up = [s for s in stock_candidates if s.get("short_up")]
    stk_all_up = [s for s in stock_candidates
                  if s.get("long_up") and s.get("mid_up") and s.get("short_up")]

    log.info(f"  候选池: {len(stock_candidates)} 只")
    log.info(f"  其中:")
    log.info(f"    长期上升: {len(stk_long_up)} 只")
    log.info(f"    中期上升: {len(stk_mid_up)} 只")
    log.info(f"    短期上升: {len(stk_short_up)} 只")
    log.info(f"    三层共振: {len(stk_all_up)} 只")

    if verbose and stock_candidates:
        log.info(f"\n  Top 10 候选个股:")
        for i, s in enumerate(stock_candidates[:10], 1):
            p = "↑" if s["long_up"] else "↓"
            m = "↑" if s["mid_up"] else "↓"
            n = "↑" if s["short_up"] else "↓"
            log.info(f"  {i:2d}. {s['code']} {s['name']:<8s} "
                     f"score={s['score']:.1f} passed={s['passed']}/7 "
                     f"长{p}中{m}短{n}")

    # ================================================================
    #  输出
    # ================================================================
    print()
    print_report(market_result, top_industries, stock_candidates)

    log.result(f"大盘: {market_result['grade']}级 长{'↑' if mkt_trend.get('prim_up') else '↓'}"
               f"中{'↑' if mkt_trend.get('sec_up') else '↓'}"
               f"短{'↑' if mkt_trend.get('min_up') else '↓'}")
    log.result(f"行业: {len(top_industries)}强 "
               f"长{len(ind_long_up)}中{len(ind_mid_up)}短{len(ind_short_up)} "
               f"共振{len(ind_all_up)} 回调{len(pullbacks)}")
    log.result(f"个股: {len(stock_candidates)}只 "
               f"长{len(stk_long_up)}中{len(stk_mid_up)}短{len(stk_short_up)} "
               f"共振{len(stk_all_up)}")
    if stock_candidates:
        for s in stock_candidates[:5]:
            log.result(f"  {s['code']} {s['name']} score={s['score']:.1f}")

    filepath = generate_report(market_result, top_industries,
                               stock_candidates, "report")
    log.info(f"  报告: {filepath}")

    t_elapsed = time.time() - t_start
    log.info(f"总耗时: {t_elapsed:.1f}s")
    log.info(f"日志: {log.get_path()}")

    dm.close()
    log.close()


if __name__ == "__main__":
    main()
