"""
单标趋势分析器 —— 搜索 + 分析 + 历史管理

用于 server.py 的 API 端点调用。
"""

import json
import os
import re
from datetime import datetime
from glob import glob

import numpy as np

REPORT_DIR = os.path.join(os.path.dirname(__file__), "report")


# ================================================================
#  搜索
# ================================================================

def search_assets(dm, query):
    """搜索股票和行业。

    参数:
        dm: DataManager 实例
        query: 用户输入的查询字符串

    返回:
        list[dict]: [{code, name, type: "stock"|"industry"}, ...]
        最多 20 条
    """
    q = query.strip()
    if not q:
        return []

    results = []

    # ---- 股票搜索 ----
    if dm._name_cache:
        for code, name in dm._name_cache.items():
            score = _match_score(code, name, q)
            if score > 0:
                results.append({"code": code, "name": name,
                                "type": "stock", "score": score})

    # ---- 行业搜索 ----
    for board in dm.get_industry_boards():
        score = _match_score(board["code"], board["name"], q)
        if score > 0:
            results.append({"code": board["code"], "name": board["name"],
                            "type": "industry", "score": score})

    # 排序：分数高（匹配度好）的在前
    results.sort(key=lambda x: x["score"], reverse=True)
    # 去重 + 取前 20
    seen = set()
    unique = []
    for r in results:
        key = (r["code"], r["type"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique[:20]


def _match_score(code, name, query):
    """计算匹配分数。越高=越匹配。0=不匹配。"""
    q = query.lower()
    c = code.lower()
    n = name.lower()

    score = 0
    # 完全代码匹配
    if c == q:
        score = 100
    # 完全名称匹配
    elif n == q:
        score = 90
    # 代码前缀匹配
    elif c.startswith(q):
        score = 80
    # 名称包含查询
    elif q in n:
        score = 70
    # 代码包含查询
    elif q in c:
        score = 60
    # 拼音首字母匹配（简单：查询全是字母时，匹配名称拼音首字母）
    elif q.isalpha() and len(q) <= 6:
        # 取名称每个字的拼音首字母
        initials = _get_initials(name)
        if q in initials:
            score = 50
    else:
        return 0

    # 短名称加分
    if len(name) <= 4 and score >= 70:
        score += 5
    return score


def _get_initials(name):
    """获取中文名称的拼音首字母（简化版）。"""
    try:
        import pypinyin
        return "".join(p[0][0] for p in pypinyin.pinyin(name, style=pypinyin.NORMAL)).lower()
    except ImportError:
        pass
    # 无 pypinyin 库时，返回原字符串（走不到拼音匹配分支）
    return ""


# ================================================================
#  单标分析
# ================================================================

def analyze_single(dm, code, asset_type):
    """对单个股票或行业运行全套趋势指标分析。

    参数:
        dm: DataManager 实例
        code: 股票代码（如 "600519"）或板块代码（如 "880001"）
        asset_type: "stock" 或 "industry"

    返回:
        dict: 完整分析结果
    """
    # 获取数据
    if asset_type == "stock":
        df = dm.get_stock_daily(code)
        name = dm.get_stock_name(code)
        is_index = False
    elif asset_type == "industry":
        df = dm.get_industry_daily(code)
        boards = dm.get_industry_boards()
        name = next((b["name"] for b in boards if b["code"] == code), code)
        is_index = False
    else:
        return {"error": f"未知类型: {asset_type}"}

    if df is None or df.empty:
        return {"error": f"无数据: {code}", "name": name, "code": code}

    # 调用统一复盘函数
    from indicators.strategies import full_review
    result = full_review(df, dm=dm, symbol=code, name=name, is_index=is_index)

    # 加时间戳和标签
    result["analyzed_at"] = datetime.now().isoformat()
    result["asset_type"] = asset_type
    result["data_rows"] = len(df)

    # 保存历史
    _save_analysis(code, result)

    return _sanitize(result)


def _save_analysis(code, result):
    """将分析结果保存到 report/single_{code}_{timestamp}.json。"""
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"single_{code}_{ts}.json"
    path = os.path.join(REPORT_DIR, filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, default=str)
    except Exception:
        pass


# ================================================================
#  格式化报告 —— 人类可读 + 说明
# ================================================================

def format_report(result, plain_text=True):
    """将单标分析结果格式化为可读文本报告（含解释说明）。

    参数:
        result: analyze_single() 返回的 dict
        plain_text: True=纯文本(CLI输出), False=HTML

    返回:
        str: 格式化后的报告
    """
    if result.get("error"):
        return f"X 分析失败: {result['error']}"

    L = []
    nl = "\n" if plain_text else "<br>\n"
    hr = "─" * 60 if plain_text else "<hr>"
    h1 = lambda s: f"\n{'='*60}\n  {s}\n{'='*60}\n" if plain_text else f"<h2>{s}</h2>"
    h2 = lambda s: f"\n  【{s}】" if plain_text else f"<h3>{s}</h3>"
    kv = lambda k, v: f"  {k:<20s} {v}" if plain_text else f"<tr><td>{k}</td><td>{v}</td></tr>"

    # ---- 头部 ----
    name = result.get("name") or result.get("symbol", "?")
    tp = result.get("asset_type", "?")
    tp_cn = "股票" if tp == "stock" else "行业板块"
    L.append(h1(f"{name} ({result.get('symbol','?')}) — {tp_cn}趋势分析"))
    L.append(f"  数据天数: {result.get('data_rows', '?')}  |  "
             f"收盘: {result.get('close', '?')}  |  "
             f"日期: {str(result.get('analyzed_at', ''))[:10]}")
    L.append(f"  综合评分: {result.get('composite_score','?')}分 → "
             f"{result.get('recommendation','?')}")
    L.append(hr)

    # ---- 趋势解读 ----
    tf = result.get("three_timeframe", {})
    adx_d = result.get("adx", {})
    ma = result.get("ma_alignment", {})
    ps = result.get("price_structure", {})

    L.append(h2("趋势解读"))
    L.append("")
    prim = "↑上升" if tf.get("prim_up") else "↓下降"
    sec = "↑上升" if tf.get("sec_up") else "↓下降"
    min_ = "↑上升" if tf.get("min_up") else "↓下降"
    L.append(f"  长/中/短期趋势: {prim} / {sec} / {min_}")
    L.append(f"  状态: {tf.get('state','?')} | 动作建议: {tf.get('action','?')}")
    L.append(f"  ADX 趋势强度: {adx_d.get('adx','?')} "
             f"({'有趋势' if adx_d.get('is_trending') else '无趋势'})  "
             f"+DI={adx_d.get('plus_di','?')} -DI={adx_d.get('minus_di','?')}")
    L.append(f"  均线排列: {'多头排列' if ma.get('long_term_up') else '空头/缠绕'}")
    L.append(f"  价格结构: {'HH+HL 多头结构' if ps.get('is_bullish') else '无明确多头结构'}")
    L.append("")

    # 解释
    if tf.get("state") == "主升浪":
        L.append("  >> 解读: 长中短三层趋势全部向上，是最强的做多信号。")
        L.append("     适合正常仓位参与，止损可适当放宽。")
    elif tf.get("state") == "小回调":
        L.append("  >> 解读: 长期和中期向上，短期回调。如果在场内应继续持有；")
        L.append("     如果在场外，可等待短期趋势转向上后再入场。")
    elif tf.get("state") == "中级回调":
        L.append("  >> 解读: 长期向上但中期转弱。建议等待中期趋势重新转向上")
        L.append("     再入场。此时追入容易被套。")
    elif tf.get("state") == "回调结束":
        L.append("  >> 解读: 长期向上，中期尚未确认但短期已转强。这是回调后")
        L.append("     的试探性入场时机。可轻仓试多，中期确认后加仓。")
    elif tf.get("state", "").startswith("熊市") or tf.get("state", "").startswith("反弹"):
        L.append("  >> 解读: 长期趋势向下，任何短期上涨都只是反弹。不建议参与做多。")
    L.append(hr)

    # ---- 风险提示 ----
    exh = result.get("exhaustion", {})
    acc = result.get("acceleration", {})
    osc = result.get("oscillation", {})
    pvr = result.get("pullback_vs_reversal", {})
    vol = result.get("volume", {})
    emerge = result.get("emergence", {})

    L.append(h2("风险与质量"))
    L.append("")
    # 过热
    if exh.get("is_exhausted"):
        lv = exh.get("exhaustion_level", 0)
        L.append(f"  [!] 见顶信号: {lv}级 ({', '.join(exh.get('signals', []))})")
        if lv >= 2:
            L.append("     → 建议: 趋势末端风险较高，不宜新建仓位，已有仓位应收紧止损。")
    else:
        L.append(f"  [OK] 无见顶信号")

    # 加速
    if acc.get("is_accelerating"):
        d = acc.get("direction", "")
        L.append(f"  >> 加速信号: {d}向加速 (涨速比={acc.get('accel_ratio','?')})")
        if d == "up":
            L.append("     → 加速上涨可能是赶顶信号，注意冲高回落风险。")
    else:
        L.append(f"  [OK] 无加速异常")

    # 回调/反转
    cls = pvr.get("classification", "?")
    L.append(f"  -> 阶段判断: {cls}")
    if cls == "确认反转":
        L.append("     → 警告: 前低已破+反弹无力，原有趋势可能已经结束。应立即止损。")
    elif cls == "可能反转":
        L.append("     → 注意: 出现反转迹象，密切关注。建议收紧止损。")
    elif cls == "回调":
        L.append("     → 正常回调，趋势结构未破坏。回调是加仓/入场的机会。")

    # 震荡
    if osc.get("should_avoid_trend_strategy"):
        L.append(f"  [!] 震荡市警告: 趋势策略在此环境下容易连续止损，建议暂停。")
    else:
        L.append(f"  [OK] 非震荡市，适合趋势策略。")

    # 趋势初现
    if emerge.get("is_emerging"):
        L.append(f"  ^^ 趋势初现: ADX刚上穿阈值，趋势可能正在形成。可试探性入场。")
    L.append(hr)

    # ---- 量价 ----
    L.append(h2("量价分析"))
    L.append("")
    L.append(f"  量价配合: {'健康' if vol.get('is_healthy') else '不健康'}")
    L.append(f"  量比: {vol.get('volume_ratio', '?')}")
    L.append("")
    if vol.get("is_healthy"):
        L.append("  >> 上涨放量/下跌缩量 = 买方主导，趋势可靠。")
    else:
        L.append("  >> 量价背离 = 趋势可能缺乏持续性，需谨慎。")
    L.append(hr)

    # ---- 止损参考 ----
    exi = result.get("exit", {})
    L.append(h2("止损/止盈参考"))
    L.append("")
    L.append(f"  当前价: {result.get('close', '?')}")
    L.append(f"  吊灯止损(从高点-3ATR): {exi.get('chandelier_stop', '?')}")
    L.append(f"  ATR移动止损: {exi.get('atr_trail_stop', '?')}")
    if exi.get("should_exit"):
        L.append(f"  [!] 建议退出: {', '.join(exi.get('reasons', []))}")
    else:
        L.append(f"  暂无需退出。")
    L.append(hr)

    return nl.join(L)


# ================================================================
#  批量分析
# ================================================================

def batch_analyze(dm, codes, asset_type="stock"):
    """批量分析多个标的，输出对比报告。

    用法:
        dm = DataManager()
        # 分析多只股票
        results = batch_analyze(dm, ["600519", "000858", "000568"], "stock")
        print(format_batch_report(results))

        # 分析多个行业
        results = batch_analyze(dm, ["880001", "880002", "880491"], "industry")
        print(format_batch_report(results))

    返回:
        list[dict]: 每个标的的分析结果列表
    """
    results = []
    for i, code in enumerate(codes, 1):
        print(f"  [{i}/{len(codes)}] 分析 {code}...", end=" ", flush=True)
        r = analyze_single(dm, code, asset_type)
        if r.get("error"):
            print(f"失败: {r['error']}")
        else:
            name = r.get("name", code)
            score = r.get("composite_score", "?")
            rec = r.get("recommendation", "?")
            print(f"完成 — {name} {score}分 {rec}")
        results.append(r)
    return results


def format_batch_report(results):
    """将批量分析结果格式化为对比表格。

    返回:
        str: 格式化后的对比报告
    """
    sep = "─" * 100
    lines = [sep]
    lines.append(f"  {'代码':<10s} {'名称':<12s} {'评分':>6s} "
                 f"{'推荐':<8s} {'趋势状态':<10s} "
                 f"{'长':>3s}{'中':>3s}{'短':>3s}  "
                 f"{'ADX':>6s} {'见顶':>4s} {'加速':>4s} {'震荡':>4s} {'量价':>4s}")
    lines.append(sep)

    for r in results:
        if r.get("error"):
            lines.append(f"  {r.get('symbol','?')[:10]:<10s} {'ERROR':<12s} "
                         f"{r['error'][:40]}")
            continue

        tf = r.get("three_timeframe", {})
        adx_d = r.get("adx", {})
        exh = r.get("exhaustion", {})
        acc = r.get("acceleration", {})
        osc = r.get("oscillation", {})
        vol = r.get("volume", {})

        p = "↑" if tf.get("prim_up") else "↓"
        s = "↑" if tf.get("sec_up") else "↓"
        m = "↑" if tf.get("min_up") else "↓"

        lines.append(
            f"  {r.get('symbol','?')[:10]:<10s} "
            f"{r.get('name','?')[:12]:<12s} "
            f"{r.get('composite_score','?'):>6} "
            f"{r.get('recommendation','?')[:8]:<8s} "
            f"{tf.get('state','?')[:10]:<10s} "
            f"{p:>3s}{s:>3s}{m:>3s}  "
            f"{adx_d.get('adx','?'):>6} "
            f"{exh.get('exhaustion_level','?'):>4} "
            f"{'⏩' if acc.get('is_accelerating') else '  ':>4s} "
            f"{'⚠' if osc.get('should_avoid_trend_strategy') else '  ':>4s} "
            f"{'OK' if vol.get('is_healthy') else '!!':>4s}"
        )

    lines.append(sep)
    lines.append(f"  共 {len(results)} 个标的")
    return "\n".join(lines)


# ================================================================
#  历史
# ================================================================

def list_analyses():
    """列出所有历史单标分析。"""
    os.makedirs(REPORT_DIR, exist_ok=True)
    files = sorted(glob(os.path.join(REPORT_DIR, "single_*.json")),
                   reverse=True)
    result = []
    for f in files:
        fname = os.path.basename(f)
        # 从文件名提取: single_{code}_{date}_{time}.json
        parts = fname.replace("single_", "").replace(".json", "").split("_")
        code = parts[0] if parts else "?"
        date_str = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:8]}" if len(parts) >= 2 else "?"
        time_str = f"{parts[2][:2]}:{parts[2][2:4]}" if len(parts) >= 3 else "?"
        size = os.path.getsize(f)
        result.append({
            "filename": fname, "code": code,
            "date": date_str, "time": time_str, "size": size,
        })
    return result


def load_analysis(filename):
    """加载指定历史分析。"""
    path = os.path.join(REPORT_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ================================================================
#  工具
# ================================================================

def _sanitize(obj):
    """递归将 numpy 类型转为原生 Python 类型，确保 JSON 可序列化。"""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# ================================================================
#  CLI 入口
# ================================================================

if __name__ == "__main__":
    import sys
    from data.manager import DataManager

    if len(sys.argv) < 2:
        print("Trend Analyzer CLI")
        print("  单个: python analyzer.py <code> [stock|industry]")
        print("  批量: python analyzer.py --batch <code1> <code2> ...")
        print("  搜索: python analyzer.py --search <keyword>")
        sys.exit(0)

    dm = DataManager()

    if sys.argv[1] == "--search":
        kw = sys.argv[2] if len(sys.argv) > 2 else ""
        for i, r in enumerate(search_assets(dm, kw)[:20], 1):
            tp = "stock" if r["type"] == "stock" else "ind"
            print(f"  {i:2d}. {r['code']}  {r['name']}  ({tp})")

    elif sys.argv[1] == "--batch":
        codes = sys.argv[2:]
        if codes:
            results = batch_analyze(dm, codes, "stock")
            print(format_batch_report(results))

    else:
        code = sys.argv[1]
        tp = sys.argv[2] if len(sys.argv) > 2 else "stock"
        result = analyze_single(dm, code, tp)
        print(format_report(result))

    dm.close()
