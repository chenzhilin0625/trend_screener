"""数据源抽象基类"""
from abc import ABC, abstractmethod
import time, os, random, requests


class DataSource(ABC):
    """所有数据源必须实现的方法"""
    name: str = "base"

    def __init__(self, delay=0.1, timeout=10):
        self.delay = delay
        self.timeout = timeout

    @abstractmethod
    def is_available(self) -> bool:
        """探测是否可用"""
        ...

    @abstractmethod
    def can_fetch_stocks(self) -> bool:
        ...

    @abstractmethod
    def can_fetch_sectors(self) -> bool:
        ...

    @abstractmethod
    def can_fetch_etfs(self) -> bool:
        ...

    @abstractmethod
    def fetch_kline(self, code, days=5) -> list[dict] | None:
        """返回 [{date,open,close,high,low,volume}, ...]"""
        ...

    @abstractmethod
    def fetch_code_list(self) -> list[dict] | None:
        """返回所有股票代码 [{code,name,market,...}]"""
        ...

    def probe_latest_date(self):
        """返回 API 最新交易日期 YYYYMMDD 或 None。默认返回 None。"""
        return None

    def _http(self, url, params=None, headers=None, timeout=None):
        time.sleep(self.delay + random.uniform(0, self.delay * 0.5))
        try:
            resp = requests.get(
                url, params=params,
                headers=headers or self._default_headers(),
                timeout=timeout or self.timeout,
            )
            resp.raise_for_status()
            return resp
        except Exception:
            return None

    @staticmethod
    def _default_headers():
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    @staticmethod
    def _sf(v):
        """safe float"""
        if v is None or v in ("-", ""): return None
        try: return float(v)
        except: return None


def get_available_source(preferred=None):
    """按优先级返回第一个可用的数据源"""
    from trend.source.eastmoney import EastMoneySource
    from trend.source.tencent import TencentSource
    from trend.source.sina import SinaSource

    sources = {
        "eastmoney": EastMoneySource(),
        "tencent": TencentSource(),
        "sina": SinaSource(),
    }
    order = preferred or ["eastmoney", "tencent", "sina"]
    for name in order:
        src = sources.get(name)
        if src and src.is_available():
            return src
    return None
