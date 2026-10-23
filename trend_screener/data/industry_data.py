"""行业板块数据接口 —— 纯本地版（通达信 880xxx 板块）"""

try:
    from data.tdx_sync import get_board_names
except ImportError:
    get_board_names = lambda: {}


def get_all_industry_data(dm, lookback_days=500):
    """获取所有行业板块日线数据。

    返回:
        dict: {board_code: {"name": str, "df": DataFrame}}
        如 {"880491": {"name": "半导体", "df": ...}}
    """
    boards = dm.get_industry_boards()
    names = get_board_names()
    result = {}
    for b in boards:
        code = b["code"]
        name = names.get(str(code), b.get("name", code))
        df = dm.get_industry_daily(code)
        if df is not None and not df.empty:
            result[code] = {
                "name": name,
                "df": df.tail(lookback_days).copy(),
            }
    return result


def get_industry_returns(dm, code):
    """获取单个行业板块的日收益率序列。"""
    df = dm.get_industry_daily(code)
    if df is None or df.empty:
        return None
    return df["close"].pct_change().dropna()


def get_industry_consistency(dm, board_code, lookback=60):
    """计算行业内成分股的均线多头排列一致性。

    返回:
        float: 0.0 ~ 1.0，行业内 MA20 > MA60 的个股占比
    """
    members = dm.get_industry_cons(board_code)
    if not members:
        return 0.0

    import pandas as pd
    bullish = 0
    valid = 0
    for code in members:
        df = dm.get_stock_daily(code)
        if df is None or len(df) < lookback:
            continue
        valid += 1
        close = df["close"]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]
        if pd.notna(ma20) and pd.notna(ma60) and ma20 > ma60:
            bullish += 1

    if valid == 0:
        return 0.0
    return bullish / valid


def map_to_sw_category(board_name):
    """将板块名称粗略映射到申万一级大类。"""
    keyword_map = {
        "银行": "银行", "保险": "非银金融", "券商": "非银金融",
        "房地产": "房地产", "建筑": "建筑装饰", "建材": "建筑材料",
        "水泥": "建筑材料", "钢铁": "钢铁", "有色": "有色金属",
        "煤炭": "煤炭", "石油": "石油石化", "化工": "基础化工",
        "电力": "公用事业", "水务": "公用事业", "环保": "公用事业",
        "燃气": "公用事业", "港口": "交通运输", "航空": "交通运输",
        "公路": "交通运输", "铁路": "交通运输", "物流": "交通运输",
        "汽车": "汽车", "新能源": "电力设备", "光伏": "电力设备",
        "风电": "电力设备", "锂电": "电力设备", "电池": "电力设备",
        "电网": "电力设备", "充电桩": "电力设备", "储能": "电力设备",
        "半导体": "电子", "芯片": "电子", "元件": "电子",
        "消费电子": "电子", "光学": "电子", "面板": "电子",
        "通信": "通信", "5G": "通信", "计算机": "计算机",
        "软件": "计算机", "传媒": "传媒", "游戏": "传媒",
        "食品": "食品饮料", "白酒": "食品饮料", "饮料": "食品饮料",
        "啤酒": "食品饮料", "乳品": "食品饮料", "调味品": "食品饮料",
        "家电": "家用电器", "纺织": "纺织服饰", "服装": "纺织服饰",
        "医药": "医药生物", "医疗": "医药生物", "中药": "医药生物",
        "生物": "医药生物", "器械": "医药生物", "农业": "农林牧渔",
        "种业": "农林牧渔", "养殖": "农林牧渔", "军工": "国防军工",
        "旅游": "社会服务", "酒店": "社会服务", "零售": "商贸零售",
        "造纸": "轻工制造", "包装": "轻工制造", "机械": "机械设备",
        "机器人": "机械设备",
    }
    for keyword, sw_name in keyword_map.items():
        if keyword in board_name:
            return sw_name
    return "其他"
