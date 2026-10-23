"""市场宽度数据接口"""


def get_breadth(dm):
    """获取市场宽度历史数据。"""
    return dm.get_market_breadth_history()


def update_breadth(dm):
    """更新当日市场宽度快照。"""
    dm.update_market_breadth()


def compute_new_high_low_ratio(dm, period=20):
    """从全市场个股日线计算新高新低比。

    注意：此函数需要全量个股数据已在本地缓存中。
    首次运行需先执行 --init。

    参数:
        dm: DataManager
        period: 回顾天数（默认20日）

    返回:
        list[dict]: 每日的数据，按日期排序
        [{"date": "...", "nh_count": N, "nl_count": N, "ratio": 0.xx}, ...]
    """
    # 获取全市场股票代码
    try:
        import akshare as ak
        all_stocks = ak.stock_info_a_code_name()
        codes = all_stocks["code"].astype(str).tolist()
    except Exception:
        codes = []

    if not codes:
        return []

    # 取所有股票的日线数据
    daily_data = {}
    for code in codes[:500]:  # 抽样500只以控制计算时间
        df = dm.get_stock_daily(code)
        if df is not None and len(df) >= period:
            daily_data[code] = df

    if not daily_data:
        return []

    # 计算每日新高/新低
    all_dates = set()
    for df in daily_data.values():
        all_dates.update(df.index)
    all_dates = sorted(all_dates)

    results = []
    for date in all_dates:
        nh = nl = 0
        for code, df in daily_data.items():
            if date not in df.index:
                continue
            idx = df.index.get_loc(date)
            if idx < period:
                continue
            window = df.iloc[idx - period:idx + 1]
            high = df.loc[date, "high"]
            low = df.loc[date, "low"]
            if high >= window["high"].max():
                nh += 1
            if low <= window["low"].min():
                nl += 1
        total = nh + nl
        ratio = nh / total if total > 0 else 0.5
        results.append({
            "date": date,
            "nh_count": nh,
            "nl_count": nl,
            "ratio": round(ratio, 3),
        })

    return results
