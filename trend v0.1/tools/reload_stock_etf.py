"""v0.1 个股+ETF数据重拉 (07-17至今，东方财富+防ban)"""
import sqlite3, requests, time, random
from datetime import datetime

PROXY = 'http://127.0.0.1:7890'
PROXIES = {'http': PROXY, 'https': PROXY}
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',
           'Referer': 'https://quote.eastmoney.com/',
           'Accept': '*/*', 'Accept-Language': 'zh-CN,zh;q=0.9'}
BASE_DELAY = 0.1
FIELDS = 'fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&ut=foobarbaz&klt=101&fqt=1'
BEG = '20260716'


def _fetch(url, retries=2):
    time.sleep(BASE_DELAY + random.uniform(0, 0.04))
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=10)
            if r.status_code == 200:
                d = r.json()
                if d.get('rc') == 0 and d.get('data') and d['data'].get('klines'):
                    return d['data']['klines']
                return None
            if r.status_code == 429:
                time.sleep(10 * (2 ** attempt))
            else:
                time.sleep(3)
        except:
            time.sleep(3)
    return None


def klines(secid):
    url = f'https://push2his.eastmoney.com/api/qt/stock/kline/get?{FIELDS}&secid={secid}&beg={BEG}&end={datetime.now().strftime("%Y%m%d")}'
    raw = _fetch(url)
    if not raw: return []
    result = []
    for row in raw:
        p = row.split(',')
        if len(p) >= 7:
            result.append({'date': p[0], 'open': float(p[1]), 'close': float(p[2]),
                           'high': float(p[3]), 'low': float(p[4]),
                           'volume': float(p[5]), 'amount': float(p[6])})
    return result


def main():
    t0 = time.time()
    conn = sqlite3.connect('trend_em.db')
    conn.execute("PRAGMA busy_timeout=10000")
    cur = conn.cursor()

    # 清空07-17以来的个股+ETF
    conn.execute("DELETE FROM stock_daily WHERE date >= '2026-07-17'")
    conn.execute("DELETE FROM etf_daily WHERE date >= '2026-07-17'")
    conn.commit()
    print(f'[sync] 已清空07-17之后数据')

    # ---- 个股 ----
    cur.execute("SELECT code FROM stock_list ORDER BY code")
    codes = [r[0] for r in cur.fetchall()]
    n = len(codes)
    print(f'[sync] 个股 {n} 只')

    total, fail, ban = 0, 0, 0
    for i, code in enumerate(codes):
        mkt = '1' if code.startswith(('6','5','9')) else '0'
        rows = klines(f'{mkt}.{code}')
        if not rows:
            fail += 1
            if fail > 20:
                print(f'  [BAN] 连续{fail}次失败, 暂停60s')
                time.sleep(60); fail = 0; ban += 1
            continue
        fail = 0
        for r in rows:
            cur.execute(
                'INSERT OR REPLACE INTO stock_daily '
                '(code,date,period,open,close,high,low,volume,amount) '
                'VALUES(?,?,?,?,?,?,?,?,?)',
                (code, r['date'], 'D', r['open'], r['close'],
                 r['high'], r['low'], r['volume'], r['amount']))
            total += 1
        if (i+1) % 500 == 0:
            conn.commit()
            print(f'  stock {i+1}/{n} {time.time()-t0:.0f}s')

    conn.commit()
    print(f'  stock done: {total} 行 fail={fail}')

    # ---- ETF ----
    cur.execute("SELECT code FROM etf_list ORDER BY code")
    etfs = [r[0] for r in cur.fetchall()]
    etf_total, etf_fail = 0, 0
    print(f'[sync] ETF {len(etfs)} 只')

    for i, code in enumerate(etfs):
        mkt = '1' if code.startswith(('5','6','9')) else '0'
        rows = klines(f'{mkt}.{code}')
        if not rows:
            etf_fail += 1; continue
        for r in rows:
            cur.execute(
                'INSERT OR REPLACE INTO etf_daily '
                '(code,date,period,open,close,high,low,volume,amount) '
                'VALUES(?,?,?,?,?,?,?,?,?)',
                (code, r['date'], 'D', r['open'], r['close'],
                 r['high'], r['low'], r['volume'], r['amount']))
            etf_total += 1
        if (i+1) % 200 == 0:
            conn.commit()
            print(f'  etf {i+1}/{len(etfs)} {time.time()-t0:.0f}s')

    conn.commit()

    # 验证
    for t in ['stock_daily', 'etf_daily']:
        cur.execute(f"SELECT MAX(date), COUNT(DISTINCT code) FROM {t} WHERE date>='2026-07-24'")
        r = cur.fetchone()
        print(f'{t}: {r[1]}只到{r[0]}')
    conn.close()
    print(f'[sync] 完成 {time.time()-t0:.0f}s ban={ban}')


if __name__ == '__main__':
    main()
