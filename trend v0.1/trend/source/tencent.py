"""腾讯财经数据源（个股 + ETF，不支持板块）"""
from trend.source.base import DataSource

KLINE_URL = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


class TencentSource(DataSource):
    name = "tencent"

    def __init__(self, delay=0.1, timeout=10):
        super().__init__(delay, timeout)

    def is_available(self) -> bool:
        resp = self._http(KLINE_URL, {
            "param": "sh600519,day,,,3,qfq",
        }, headers={"Referer": "https://gu.qq.com/"})
        if not resp: return False
        try:
            data = resp.json()
            return data.get("code") == 0 and bool(
                data.get("data", {}).get("sh600519", {}).get("qfqday"))
        except Exception:
            return False

    def can_fetch_stocks(self): return True
    def can_fetch_sectors(self): return False
    def can_fetch_etfs(self): return True  # 仅上海 ETF

    def fetch_kline(self, code, days=5):
        tc = self._tc(code)
        resp = self._http(KLINE_URL, {
            "param": f"{tc},day,,,{days},qfq",
        }, headers={"Referer": "https://gu.qq.com/"})
        if not resp: return None
        klines = resp.json().get("data", {}).get(tc, {}).get("qfqday") or []
        rows = []
        for p in klines:
            if len(p) < 6: continue
            rows.append({"code": code, "date": p[0], "period": "D",
                         "open": self._sf(p[1]), "close": self._sf(p[2]),
                         "high": self._sf(p[3]), "low": self._sf(p[4]),
                         "volume": self._sf(p[5]),
                         "amount": None, "amplitude": None,
                         "change_pct": None, "turnover": None})
        return rows

    def fetch_code_list(self):
        return None  # 不支持

    @staticmethod
    def _tc(code):
        return ("sh" if code.startswith(("6", "68", "5")) else "sz") + code
