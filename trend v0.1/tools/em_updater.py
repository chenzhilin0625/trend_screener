"""v0.1 东方财富板块K线更新（修复版 + 防ban）"""
import sqlite3, requests, time, random
from datetime import datetime, timedelta

PROXY = 'http://127.0.0.1:7890'
PROXIES = {'http': PROXY, 'https': PROXY}
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',
           'Referer': 'https://quote.eastmoney.com/',
           'Accept': '*/*', 'Accept-Language': 'zh-CN,zh;q=0.9'}
BASE_DELAY = 0.12  # 基础间隔
RETRY_DELAY = 5     # 失败重试间隔
KLINE_FIELDS = 'fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&ut=foobarbaz&klt=101&fqt=1'


def _fetch(url, timeout=10, retries=2):
    """带重试和随机延迟的请求"""
    for attempt in range(retries + 1):
        # 随机延迟防检测
        time.sleep(BASE_DELAY + random.uniform(0, 0.05))
        try:
            r = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=timeout)
            if r.status_code == 200:
                d = r.json()
                if d.get('rc') == 0 and d.get('data'):
                    return d['data']
                # rc非0说明请求失败但不是封禁
                if d.get('rc') != 0:
                    return None
            elif r.status_code == 429:
                wait = RETRY_DELAY * (2 ** attempt)
                print(f'  [429] 限流, 等{wait}s...')
                time.sleep(wait)
            else:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            if attempt < retries:
                time.sleep(RETRY_DELAY)
    return None


def kline(secid, beg, end):
    """获取K线，返回[{date,open,close,high,low,volume,amount},...]"""
    url = f'https://push2his.eastmoney.com/api/qt/stock/kline/get?{KLINE_FIELDS}&secid={secid}&beg={beg}&end={end}'
    data = _fetch(url)
    if not data or not data.get('klines'):
        return []
    result = []
    for row in data['klines']:
        parts = row.split(',')
        if len(parts) >= 7:
            result.append({
                'date': parts[0], 'open': float(parts[1]),
                'close': float(parts[2]), 'high': float(parts[3]),
                'low': float(parts[4]), 'volume': float(parts[5]),
                'amount': float(parts[6]),
            })
    return result


def main():
    t0 = time.time()
    conn = sqlite3.connect('trend_em.db')
    conn.execute("PRAGMA busy_timeout=10000")
    cur = conn.cursor()

    # 日期范围
    cur.execute("SELECT MAX(date) FROM sector_daily")
    db_latest = cur.fetchone()[0] or '2026-07-16'
    today = datetime.now().strftime('%Y%m%d')
    beg = db_latest.replace('-', '')[:8]
    print(f'[sync] 板块K线: {beg} -> {today}')

    # 获取所有BK板块
    cur.execute("SELECT code, name FROM sector_list WHERE code LIKE 'BK%'")
    sectors = cur.fetchall()
    print(f'[sync] {len(sectors)} 个板块')

    total, fail, ban = 0, 0, 0
    for i, (code, name) in enumerate(sectors):
        # secid: 90.BKxxxx (保留BK前缀！)
        secid = f'90.{code}'
        rows = kline(secid, beg, today)

        if not rows:
            fail += 1
            if fail > 20:  # 连续失败过多，可能被ban
                print(f'  [BAN] 连续{fail}次失败, 暂停60s...')
                time.sleep(60)
                fail = 0
                ban += 1
            continue
        fail = 0  # 重置连续失败

        for r in rows:
            cur.execute(
                'INSERT OR REPLACE INTO sector_daily '
                '(code,date,period,open,close,high,low,volume,amount) '
                'VALUES(?,?,?,?,?,?,?,?,?)',
                (code, r['date'], 'D', r['open'], r['close'],
                 r['high'], r['low'], r['volume'], r['amount']))
            total += 1

        if (i + 1) % 100 == 0:
            conn.commit()
            elapsed = time.time() - t0
            print(f'  [{i+1}/{len(sectors)}] {total}行 {elapsed:.0f}s fail={fail}')

    conn.commit()

    # 验证
    cur.execute('SELECT MAX(date), COUNT(DISTINCT code) FROM sector_daily WHERE date >= ?',
                (db_latest,))
    print(f'[sync] 完成: {cur.fetchone()}, 耗时{time.time()-t0:.0f}s ban={ban}')
    conn.close()


if __name__ == '__main__':
    main()
