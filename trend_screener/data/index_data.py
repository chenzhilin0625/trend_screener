"""大盘指数数据接口"""

from config import MARKET_INDICES, PRIMARY_INDEX


def get_primary_index(dm):
    """获取主对比基准（沪深300）日线。"""
    return dm.get_index_daily(PRIMARY_INDEX)


def get_all_market_indices(dm):
    """获取所有需要监测的大盘指数日线。"""
    result = {}
    for idx in MARKET_INDICES:
        df = dm.get_index_daily(idx["code"])
        if df is not None and not df.empty:
            result[idx["name"]] = df
    return result


def get_benchmark_returns(dm, symbol=None):
    """获取基准指数日收益率序列。"""
    sym = symbol or PRIMARY_INDEX
    df = dm.get_index_daily(sym)
    if df is None or df.empty:
        return None
    return df["close"].pct_change().dropna()
