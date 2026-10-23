"""东方财富 push2 数据源"""
import os, time, random, requests
from datetime import datetime, timedelta
from trend.source.base import DataSource

KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
LIST_URL = "https://push2.eastmoney.com/webguest/api/qt/clist/get"


class EastMoneySource(DataSource):
    name = "eastmoney"

    def __init__(self, delay=0.1, timeout=10):
        super().__init__(delay, timeout)
        for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            os.environ.pop(k, None)
        os.environ["NO_PROXY"] = "*"

    def _http(self, url, params=None, headers=None, timeout=None, retries=3):
        """覆盖基类：绕过系统代理 + 重试 + curl 兜底"""
        for attempt in range(retries):
            time.sleep(self.delay + random.uniform(0, self.delay * 0.5))
            try:
                resp = requests.get(
                    url, params=params,
                    headers=headers or self._default_headers(),
                    timeout=timeout or self.timeout,
                    proxies={"http": None, "https": None},
                )
                resp.raise_for_status()
                return resp
            except Exception:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        import subprocess
        import json as _json
        try:
            qs = "&".join(f"{k}={v}" for k, v in (params or {}).items())
            full_url = f"{url}?{qs}" if qs else url
            h = headers or self._default_headers()
            t = timeout or self.timeout
            r = subprocess.run(
                ["curl", "-s", "--connect-timeout", str(t),
                 "-H", f"User-Agent: {h.get('User-Agent', '')}", full_url],
                capture_output=True, text=True, timeout=t + 5,
            )
            if r.returncode == 0 and r.stdout.strip():
                class _R:
                    def __init__(self, text): self._text = text
                    def json(self): return _json.loads(self._text)
                    @property
                    def text(self): return self._text
                return _R(r.stdout)
        except Exception:
            pass

        return None

    def is_available(self) -> bool:
        resp = self._http(KLINE_URL, {
            "secid": "1.600519", "fields1": "f1", "fields2": "f51",
            "klt": "101", "fqt": "1",
            "beg": (datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
            "end": datetime.now().strftime("%Y%m%d"),
        }, timeout=5, retries=1)
        if not resp: return False
        try:
            data = resp.json()
            return data.get("rc") == 0 and bool(data.get("data", {}).get("klines"))
        except Exception:
            return False

    def can_fetch_stocks(self): return True
    def can_fetch_sectors(self): return True
    def can_fetch_etfs(self): return True

    def probe_latest_date(self):
        """返回 API 最新交易日期 YYYYMMDD 或 None"""
        resp = self._http(KLINE_URL, {
            "secid": "1.600519", "fields1": "f1", "fields2": "f51",
            "klt": "101", "fqt": "1",
            "beg": (datetime.now() - timedelta(days=10)).strftime("%Y%m%d"),
            "end": datetime.now().strftime("%Y%m%d"),
        })
        if not resp: return None
        klines = resp.json().get("data", {}).get("klines") or []
        return klines[-1].split(",")[0].replace("-", "") if klines else None

    def fetch_kline(self, code, days=5):
        secid = self._secid(code)
        beg = (datetime.now() - timedelta(days=max(days + 5, 30))).strftime("%Y%m%d")
        end = datetime.now().strftime("%Y%m%d")
        resp = self._http(KLINE_URL, {
            "secid": secid, "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101", "fqt": "1", "beg": beg, "end": end,
        })
        if not resp: return None
        klines = resp.json().get("data", {}).get("klines") or []
        rows = []
        for line in klines:
            p = line.split(",")
            if len(p) < 11 or p[2] in ("-", ""): continue
            rows.append({"code": code, "date": p[0], "period": "D",
                         "open": self._sf(p[1]), "close": self._sf(p[2]),
                         "high": self._sf(p[3]), "low": self._sf(p[4]),
                         "volume": self._sf(p[5]), "amount": self._sf(p[6]),
                         "amplitude": self._sf(p[7]), "change_pct": self._sf(p[8]),
                         "turnover": self._sf(p[10])})
        return rows

    def fetch_code_list(self):
        items = self._fetch_all_pages(LIST_URL, {
            "po": "1", "np": "1", "fltt": "2", "invt": "2", "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f9,f10,f12,f13,f14,f20,f21,f23,f26,f100,f103,f117",
        })
        if not items: return None
        return [{"code": i["f12"], "name": i.get("f14", ""),
                 "market": str(i.get("f13", "1")),
                 "industry": i.get("f100", ""),
                 "listing_date": i.get("f26"),
                 "total_mcap": self._sf(i.get("f20")),
                 "circ_mcap": self._sf(i.get("f21")),
                 "pe_static": self._sf(i.get("f23")),
                 "pe_dynamic": self._sf(i.get("f9")),
                 "price": self._sf(i.get("f2")),
                 "change_pct": self._sf(i.get("f3")),
                 "turnover": self._sf(i.get("f117"))} for i in items]

    def fetch_sector_list(self):
        result = []
        for fs, stype in [("m:90+t:2", "industry"), ("m:90+t:3", "concept")]:
            items = self._fetch_all_pages(LIST_URL, {
                "po": "1", "np": "1", "fltt": "2", "invt": "2", "fid": "f3",
                "fs": fs, "fields": "f2,f3,f12,f14,f20,f21",
            })
            if items:
                for i in items:
                    result.append({"code": i["f12"], "name": i.get("f14", ""),
                                   "sector_type": stype,
                                   "total_mcap": self._sf(i.get("f20")),
                                   "circ_mcap": self._sf(i.get("f21")),
                                   "price": self._sf(i.get("f2")),
                                   "change_pct": self._sf(i.get("f3"))})
        return result if result else None

    def fetch_etf_list(self):
        """拉取全部 ETF 列表"""
        items = self._fetch_all_pages(LIST_URL, {
            "po": "1", "np": "1", "fltt": "2", "invt": "2", "fid": "f3",
            "fs": "b:MK0021,b:MK0022,b:MK0023,b:MK0024",
            "fields": "f2,f3,f12,f14,f20,f21",
        })
        if not items:
            return None
        return [{"code": i["f12"], "name": i.get("f14", ""),
                 "price": self._sf(i.get("f2")),
                 "change_pct": self._sf(i.get("f3")),
                 "fund_size": self._sf(i.get("f20"))} for i in items]

    @staticmethod
    def _secid(code):
        if code.startswith("BK"): return f"90.{code}"
        return f"1.{code}" if code.startswith(("6", "68")) else f"0.{code}"

    def _fetch_all_pages(self, url, params, batch=500):
        results, page = [], 1
        while True:
            p = {**params, "pn": str(page), "pz": str(batch)}
            resp = self._http(url, p, timeout=15)
            if not resp: break
            data = resp.json()
            items = data.get("data", {}).get("diff") or []
            total = data.get("data", {}).get("total", 0)
            if not items: break
            results.extend(items)
            if len(results) >= total: break
            page += 1
        return results
