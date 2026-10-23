"""东方财富 API 连通性测试"""
import os, requests, time

for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "*"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

TESTS = [
    ("push2his K线", "https://push2his.eastmoney.com/api/qt/stock/kline/get",
     {"secid": "1.600519", "fields1": "f1", "fields2": "f51", "klt": "101",
      "fqt": "1", "beg": "20260701", "end": "20260723"}),
    ("push2 列表", "https://push2.eastmoney.com/api/qt/clist/get",
     {"pn": "1", "pz": "1", "fields": "f2,f12,f14", "fs": "m:0+t:6"}),
]

ok = fail = 0
for label, url, params in TESTS:
    try:
        t0 = time.time()
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        elapsed = time.time() - t0
        if resp.status_code == 200:
            data = resp.json()
            rc = data.get("rc", -1)
            print(f"[OK]   {label}: 200  rc={rc}  {elapsed:.1f}s")
            ok += 1
        else:
            print(f"[WARN] {label}: {resp.status_code}  {elapsed:.1f}s")
            fail += 1
    except Exception as e:
        elapsed = time.time() - t0
        print(f"[FAIL] {label}: {type(e).__name__}  {elapsed:.1f}s")
        fail += 1

print(f"\n{ok}/{len(TESTS)} ok, {fail}/{len(TESTS)} fail")
