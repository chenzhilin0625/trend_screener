"""个股数据接口 —— 纯本地版"""

from data.tdx_sync import get_stock_industry_map


def get_stock_batch(dm, codes, lookback_days=250):
    """批量获取个股日线。"""
    result = {}
    for code in codes:
        df = dm.get_stock_daily(code)
        if df is not None and not df.empty:
            result[code] = df.tail(lookback_days).copy()
    return result


def get_stocks_in_industries(dm, board_codes):
    """获取多个行业板块的成分股代码集合。

    通过 tdxhy.cfg 映射反查。
    """
    all_codes = set()
    stock_ind_map = get_stock_industry_map()
    for bc in board_codes:
        for stock_code, inds in stock_ind_map.items():
            all_codes.add(stock_code)
    return all_codes
