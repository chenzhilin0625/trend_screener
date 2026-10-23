"""ROC 动量 + ID 强度指标"""
_SECTOR_FILTER = [
    "昨日涨停", "昨日连板", "昨日触板", "昨日首板",
    "涨停", "连板", "一字板", "曾涨停", "炸板", "打板", "封板", "触板",
]


def _skip(name):
    return any(kw in name for kw in _SECTOR_FILTER)


def roc(close, period):
    """ROC = 最新价 / N 日前价 - 1"""
    need = period + 1
    if len(close) < need:
        return None
    return float(close.iloc[-1] / close.iloc[-need] - 1)


def id_score(close, period_days, skip_recent):
    """ID = (跌天数% − 涨天数%)，只含窗口上涨标的"""
    total_window = period_days + skip_recent
    if len(close) < total_window + 1:
        return None
    recent = close.iloc[-total_window:-skip_recent]
    diff = recent.diff().iloc[1:]
    total_days = len(diff)
    if total_days == 0:
        return None
    total_return = float(recent.iloc[-1] / recent.iloc[0] - 1)
    if total_return <= 0:
        return None
    up = (diff > 0).sum()
    down = (diff < 0).sum()
    return (down - up) / total_days


def _sf(v):
    if v is None or str(v) in ("", "-", "None"):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _rank(records, top_n, rank_by):
    if rank_by == "id":
        records[:] = [r for r in records
                      if r.get("roc") is not None and r["roc"] > 0
                      and r.get("id") is not None]
        records.sort(key=lambda x: x["id"])
    else:
        records.sort(key=lambda x: x.get("roc") or -999, reverse=True)
    for i, r in enumerate(records[:top_n]):
        r["rank"] = i + 1


# ---- 公开排名接口 ----

def _skip_for(period):
    """ID 剔除映射：20→1, 60→5, 120→20"""
    return {20: 1, 60: 5, 120: 20}.get(period, 20)


def rank_sectors(loader, period=20, top_n=10, sector_type=None, rank_by="roc"):
    skip = _skip_for(period)
    records = []
    for code, name, df in loader.load_all_sector_data(sector_type=sector_type):
        if _skip(name):
            continue
        close = df["close"].astype(float)
        if len(close) < period + 1:
            continue
        records.append({
            "code": code, "name": name,
            "roc": roc(close, period),
            "id": id_score(close, period, skip),
        })
    _rank(records, top_n, rank_by)
    return records[:top_n]


def rank_stocks(loader, period=20, top_n=30, rank_by="roc"):
    skip = _skip_for(period)
    stock_meta = loader.get_stock_list_df()
    meta_dict = {str(r["code"]): r for _, r in stock_meta.iterrows()}
    records = []
    for code, df in loader.load_all_stocks():
        meta = meta_dict.get(str(code))
        if meta is None:
            continue
        close = df["close"].astype(float)
        if len(close) < period + 1:
            continue
        records.append({
            "code": code,
            "name": str(meta.get("name", code)),
            "roc": roc(close, period),
            "id": id_score(close, period, skip),
        })
    _rank(records, top_n, rank_by)
    return records[:top_n]


def rank_etfs(loader, period=20, top_n=10, rank_by="roc"):
    skip = _skip_for(period)
    records = []
    for code, df in loader.load_all_etfs():
        close = df["close"].astype(float)
        if len(close) < period + 1:
            continue
        records.append({
            "code": code, "name": loader.get_etf_name(code),
            "roc": roc(close, period),
            "id": id_score(close, period, skip),
        })
    _rank(records, top_n, rank_by)
    return records[:top_n]


def rank_sector_detail(loader, bk_code, period=20, top_n=20):
    row = loader.conn.execute(
        "SELECT name FROM sector_list WHERE code=?", (bk_code,)).fetchone()
    if not row:
        return None, []
    records = []
    for code in loader.get_concept_members(bk_code):
        df = loader.load_stock(code)
        if df is None or len(df) < period + 1:
            continue
        close = df["close"].astype(float)
        records.append({
            "code": code, "name": loader.get_stock_name(code),
            "roc": roc(close, period),
        })
    records.sort(key=lambda x: x.get("roc") or -999, reverse=True)
    top = records[:top_n]
    for i, r in enumerate(top):
        r["rank"] = i + 1
    return row[0], top
