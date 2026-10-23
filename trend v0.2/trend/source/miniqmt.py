"""MiniQMT (xtquant) 数据源 — 本地行情，零封禁"""
import numpy as np
import pandas as pd
from xtquant import xtdata


class MiniQMTSource:
    """MiniQMT 本地行情数据源。需 QMT 客户端运行中。"""
    name = "miniqmt"
    _sw2_cache = None
    _sw3_cache = None

    @staticmethod
    def is_available():
        try:
            sectors = xtdata.get_sector_list()
            return len(sectors) > 0
        except Exception:
            return False

    # ---- 个股 ----

    def can_fetch_stocks(self): return True

    def fetch_stock_list(self):
        """返回沪深A股代码 + 名称，格式 {code, name, market, industry}"""
        codes = set()
        for sn in ("沪深A股", "上证A股", "深证A股"):
            for c in xtdata.get_stock_list_in_sector(sn):
                codes.add(c)
        return sorted(codes)

    def fetch_klines(self, codes, start, end):
        """批量获取日K线，返回 {code: [{date,open,close,high,low,volume,amount,change_pct}, ...]}"""
        fields = ("open","close","high","low","volume","amount","preClose")
        # 逐只下载
        for code in codes:
            try:
                xtdata.download_history_data(code, period="1d",
                    start_time=start.replace("-",""), end_time=end.replace("-",""))
            except Exception:
                pass

        # 批量获取
        data = xtdata.get_market_data(
            field_list=list(fields),
            stock_list=codes,
            period="1d",
            start_time=start.replace("-",""),
            count=-1,
        )

        result = {}
        for code in codes:
            rows = []
            close_series = data.get("close", pd.DataFrame())
            if code not in close_series.index:
                continue
            dates = [f"{str(d)[:4]}-{str(d)[4:6]}-{str(d)[6:]}" for d in close_series.columns]
            for i, date in enumerate(dates):
                if date < start or date > end:
                    continue
                row = {"code": code, "date": date, "period": "D"}
                for f in fields:
                    fd = data.get(f)
                    if fd is not None and code in fd.index:
                        val = fd.iloc[fd.index.get_loc(code), i]
                        row[f] = float(val) if not (isinstance(val, float) and np.isnan(val)) else None
                # 计算 change_pct = (close - preClose) / preClose
                pre = row.get("preClose")
                close = row.get("close")
                row["change_pct"] = (close - pre) / pre if pre and close and pre != 0 else None
                # 去掉 preClose（不需要存入 DB）
                row.pop("preClose", None)
                rows.append(row)
            result[code] = rows
        return result

    # ---- ETF ----

    def can_fetch_etfs(self): return True

    def fetch_etf_list(self):
        """返回沪深ETF代码列表"""
        codes = set()
        for sn in ("沪深ETF", "上海ETF", "深圳ETF"):
            for c in xtdata.get_stock_list_in_sector(sn):
                codes.add(c)
        return sorted(codes)

    # ---- 行业板块 (SW2/SW3，通过成分股聚合) ----

    def can_fetch_sectors(self): return True

    def fetch_sw2_list(self):
        """SW2 行业列表 [{code, name, sector_type}]"""
        if self._sw2_cache is None:
            self._sw2_cache = _load_sw_list("SW2")
        return self._sw2_cache

    def fetch_sw3_list(self):
        """SW3 行业列表"""
        if self._sw3_cache is None:
            self._sw3_cache = _load_sw_list("SW3")
        return self._sw3_cache

    def aggregate_sector_klines(self, sector_code, stock_klines, start, end, min_coverage=1.0):
        """成分股等权平均OHLC + 总成交量/额 + change_pct
        min_coverage: 某日至少多少比例的成分股有数据，否则跳过该日"""
        # 优先从 sector_member 表读取（QMT离线也能工作）
        import sqlite3 as _sql
        from trend.config import DB_PATH
        _conn = _sql.connect(DB_PATH)
        member_rows = _conn.execute("SELECT stock_code FROM sector_member WHERE sector_code=?", (sector_code,)).fetchall()
        _conn.close()
        member_codes = [r[0] for r in member_rows] if member_rows else _get_sw_members(sector_code)
        if not member_codes:
            return []
        total_members = len(member_codes)
        min_members = max(2, int(total_members * min_coverage))
        date_data = {}  # {date: {"close":[c1,..],"high":[h1,..],volume:sum,amount:sum}}
        for code in member_codes:
            # DB版member_codes已是纯代码；MiniQMT版带后缀需要_strip
            if code not in stock_klines:
                code = _match_code(code, list(stock_klines.keys()))
            if code not in stock_klines:
                continue
            for r in stock_klines.get(code, []):
                d = r["date"]
                dd = date_data.setdefault(d, {})
                for f in ("close","open","high","low"):
                    v = r.get(f)
                    if v is not None:
                        dd.setdefault(f, []).append(v)
                for f in ("volume","amount"):
                    v = r.get(f)
                    if v is not None:
                        dd[f] = dd.get(f, 0) + v
        rows = []
        prev = None
        for date in sorted(date_data.keys()):
            if date < start or date > end:
                continue
            dd = date_data[date]
            def _avg(k):
                vv = dd.get(k, [])
                return sum(vv)/len(vv) if vv else None
            c = _avg("close")
            # 覆盖率检查：当日有close的股票数 >= min_members
            if c is None or len(dd.get("close", [])) < min_members:
                continue
            rows.append({
                "code": sector_code, "date": date, "period": "D",
                "open": _avg("open") or c, "close": c,
                "high": _avg("high") or c, "low": _avg("low") or c,
                "volume": dd.get("volume"), "amount": dd.get("amount"),
                "change_pct": (c-prev)/prev if prev and prev!=0 else None,
            })
            prev = c
        return rows


# ---- 内部辅助 ----

_SW_MEMBERS = {}  # {sector_code: [member_codes]}


def _load_sw_list(prefix):
    """加载 SW2/SW3 行业列表"""
    result = []
    for s in xtdata.get_sector_list():
        if s.startswith(prefix) and "加权" not in s and "B股" not in s:
            name = s[len(prefix):]  # "SW2银行" → "银行"
            result.append({"code": s, "name": name, "sector_type": prefix.lower()})
            # 缓存成分股
            members = xtdata.get_stock_list_in_sector(s)
            _SW_MEMBERS[s] = members
    return result


def _get_sw_members(sector_code):
    return _SW_MEMBERS.get(sector_code, [])


def _match_code(sector_code_with_suffix, available_pure_codes):
    """000670.SZ → 000670（匹配 DB 中纯代码）"""
    pure = sector_code_with_suffix.split(".")[0]
    return pure if pure in available_pure_codes else None
