"""新浪财经数据源（个股 + ETF，不支持板块）"""
from trend.source.base import DataSource

KLINE_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketData.getKLineData"


class SinaSource(DataSource):
    name = "sina"

    def is_available(self) -> bool:
        resp = self._http(KLINE_URL, {
            "symbol": "sh600519", "scale": "240", "ma": "no", "datalen": "3",
        }, headers={"Referer": "https://finance.sina.com.cn"})
        if not resp: return False
        try:
            data = resp.json()
            return isinstance(data, list) and len(data) > 0
        except Exception:
            return False

    def can_fetch_stocks(self): return True
    def can_fetch_sectors(self): return False
    def can_fetch_etfs(self): return True

    def fetch_kline(self, code, days=5):
        tc = self._tc(code)
        resp = self._http(KLINE_URL, {
            "symbol": tc, "scale": "240", "ma": "no", "datalen": str(days),
        }, headers={"Referer": "https://finance.sina.com.cn"})
        if not resp: return None
        data = resp.json()
        if not isinstance(data, list): return None
        rows = []
        for d in data:
            rows.append({"code": code, "date": d["day"], "period": "D",
                         "open": self._sf(d.get("open")),
                         "close": self._sf(d.get("close")),
                         "high": self._sf(d.get("high")),
                         "low": self._sf(d.get("low")),
                         "volume": self._sf(d.get("volume")),
                         "amount": None, "amplitude": None,
                         "change_pct": None, "turnover": None})
        return rows

    def fetch_code_list(self):
        return None

    @staticmethod
    def _tc(code):
        return ("sh" if code.startswith(("6", "68", "5")) else "sz") + code
