"""v0.1 数据更新器 —— 腾讯接口（主） + 新浪（兜底），严格限速"""
import sqlite3, requests, time, json
from datetime import datetime, timedelta

DB = 'trend_em.db'
DELAY = 0.15  # 每次请求间隔（秒），腾讯 WAF 敏感
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36'}


def _connect():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _safe_get(url, params=None, timeout=10):
    time.sleep(DELAY)
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r
        if r.status_code == 501:
            print(f"  [WARN] 腾讯 WAF 501, 等30s...")
            time.sleep(30)
            return None
        return None
    except Exception as e:
        print(f"  [ERR] {str(e)[:50]}")
        time.sleep(2)
        return None


def fetch_kline_tencent(code, count=30):
    """腾讯日K: 600519 -> sh600519, 000001 -> sz000001"""
    market = "sh" if code.startswith(("5","6","9")) else "sz"
    full = f"{market}{code}"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full},day,,,{count},qfq"
    r = _safe_get(url)
    if not r:
        return []
    try:
        data = r.json()
        raw = data.get("data",{}).get(full,{}).get("qfqday") or data.get("data",{}).get(full,{}).get("day",[])
        result = []
        for row in raw:
            if len(row) >= 6:
                result.append({
                    "date": row[0],
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "volume": float(row[5]),
                    "amount": float(row[6]) if len(row) > 6 else None,
                    "period": "D",
                })
        return result
    except Exception:
        return []


def fetch_kline_sina(code, count=30):
    """新浪日K"""
    market = "sh" if code.startswith(("5","6","9")) else "sz"
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {"symbol": f"{market}{code}", "scale": 240, "ma": "no", "datalen": count}
    r = _safe_get(url, params=params)
    if not r:
        return []
    try:
        data = r.json()
        if not isinstance(data, list):
            return []
        result = []
        for d in data:
            result.append({
                "date": d["day"],
                "open": float(d["open"]),
                "close": float(d["close"]),
                "high": float(d["high"]),
                "low": float(d["low"]),
                "volume": float(d["volume"]),
                "amount": None,  # 新浪不提供额
                "period": "D",
            })
        return result
    except Exception:
        return []


def update_stocks(conn, codes, days=30):
    """更新个股最近N天K线"""
    cur = conn.cursor()
    total, fail = 0, 0
    for i, code in enumerate(codes):
        rows = fetch_kline_tencent(code, days)
        if not rows:
            rows = fetch_kline_sina(code, days)  # 兜底
            if not rows:
                fail += 1
                continue
        for r in rows:
            r["code"] = code
            cur.execute(
                "INSERT OR IGNORE INTO stock_daily "
                "(code,date,period,open,close,high,low,volume,amount) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (code, r["date"], "D", r["open"], r["close"],
                 r["high"], r["low"], r["volume"], r["amount"]))
            total += 1
        if (i+1) % 200 == 0:
            conn.commit()
            print(f"  stock {i+1}/{len(codes)} fail={fail}")
    conn.commit()
    print(f"  stock done: {total} rows, fail={fail}")
    return total


def update_etfs(conn, codes, days=30):
    """ETF同样逻辑"""
    return update_stocks(conn, codes, days)


def main():
    t0 = time.time()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM stock_daily")
    db_date = cur.fetchone()[0] or "2026-01-01"
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[update] DB最新: {db_date}, 目标: {today}")

    # 需要更新的日期数
    need_days = max(10, (datetime.now() - datetime.strptime(db_date[:10], "%Y-%m-%d")).days + 5)
    print(f"[update] 拉最近 {need_days} 天")

    # 个股
    cur.execute("SELECT code FROM stock_list ORDER BY code")
    codes = [r[0] for r in cur.fetchall()]
    print(f"[update] 个股 {len(codes)} 只")
    update_stocks(conn, codes, need_days)

    # ETF
    cur.execute("SELECT code FROM etf_list ORDER BY code")
    etf_codes = [r[0] for r in cur.fetchall()]
    print(f"[update] ETF {len(etf_codes)} 只")
    update_etfs(conn, etf_codes, need_days)

    conn.close()
    print(f"[update] 完成, 耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
