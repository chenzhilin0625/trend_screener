"""CLI 入口（argparse）"""
import sys, time, argparse
from datetime import datetime
from trend.db.loader import DataLoader
from trend.score.indicators import rank_sectors, rank_stocks, rank_etfs, rank_sector_detail
from trend.report import print_block, write_html
from trend.sync import sync_incremental, is_data_current


def main():
    p = argparse.ArgumentParser(description="ROC 动量排名 + ID 强度指标")
    p.add_argument("--sectors", action="store_true", help="仅板块")
    p.add_argument("--etf", action="store_true", help="仅 ETF")
    p.add_argument("--top", type=int, default=30, help="个股 Top N (默认 30)")
    p.add_argument("--no-report", action="store_true", help="不输出 HTML 报告")
    p.add_argument("--no-sync", action="store_true", help="跳过增量更新")
    p.add_argument("--detail", type=str, help="板块成分股 (BK代码)")
    args = p.parse_args()

    t0 = time.time()

    # 自动增量更新
    if not args.no_sync and not is_data_current():
        print("[auto] 检测到新数据，增量更新...")
        sync_incremental(verbose=True)
        print()

    loader = DataLoader()

    # 板块详情
    if args.detail:
        name, stocks = rank_sector_detail(loader, args.detail, top_n=args.top)
        if name:
            print(f"{name} ({args.detail}) 成分股 ROC(20) 排名")
            print(f"  {'':>3s} {'代码':<8s} {'名称':<10s} {'ROC':>7s} {'市值(亿)':>9s}")
            print(f"  {'-'*42}")
            for s in stocks:
                m = s.get('mcap', 0) / 1e8 if s.get('mcap') else 0
                print(f"  {s['rank']:2d}. {s['code']:<8s} {s['name']:<10s} "
                      f"{s['roc']:>6.1%} {m:>8.0f}")
        loader.close()
        return

    sections = []
    print(f"ROC 动量排名  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"DB: {loader.db_path}  市值 >= 50亿")

    # 板块
    if not args.etf:
        print(f"\n{'='*70}\n  板块动量排名\n{'='*70}")
        t_sec = time.time()
        for label, stype in [("行业", "industry"), ("概念", "concept")]:
            for period in (20, 60, 120):
                for rk in ("roc", "id"):
                    data = rank_sectors(loader, period=period, top_n=10,
                                        sector_type=stype, rank_by=rk)
                    print_block(f"{label}板块  {rk.upper()}{period}",
                                data, "{rank:2d}. {name:<8s} {roc:>8.1%}",
                                sections)
        print(f"  (板块 {time.time()-t_sec:.1f}s)")
    if args.sectors:
        loader.close(); _finish(sections, args); return

    # ETF
    if not args.sectors:
        print(f"\n{'='*70}\n  ETF 动量排名\n{'='*70}")
        t_etf = time.time()
        for period in (20, 60, 120):
            for rk in ("roc", "id"):
                data = rank_etfs(loader, period=period, top_n=10, rank_by=rk)
                print_block(f"ETF  {rk.upper()}{period}",
                            data, "{rank:2d}. {code:<8s} {name:<16s} {roc:>6.1%}",
                            sections)
        print(f"  (ETF {time.time()-t_etf:.1f}s)")
        if args.etf:
            loader.close(); _finish(sections, args); return

    # 个股
    if not args.sectors and not args.etf:
        print(f"\n{'='*70}\n  个股 动量排名 Top {args.top}\n{'='*70}")
        t_stock = time.time()
        for period in (20, 60, 120):
            for rk in ("roc", "id"):
                data = rank_stocks(loader, period=period, top_n=args.top, rank_by=rk)
                print_block(f"个股  {rk.upper()}{period}",
                            data, "{rank:2d}. {code:<8s} {name:<6s} {roc:>6.1%}",
                            sections)
        print(f"  (个股 {time.time()-t_stock:.1f}s)")

    loader.close()
    elapsed = time.time() - t0
    print(f"\n总耗时 {elapsed:.0f}s\n{'='*70}")
    _finish(sections, args)


def _finish(sections, args):
    if not args.no_report:
        write_html(sections)


if __name__ == "__main__":
    main()
