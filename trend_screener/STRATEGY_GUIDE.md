# 趋势交易者每日复盘工具箱 —— 策略使用文档

> 版本 2.2 | 2026-06-04 | 纯本地 · 零网络依赖

---

## 项目结构

```
trend_screener/
│
├── main.py                      ★ 主入口：一键运行完整分析
├── config.py                    ★ 全局参数：阈值/权重/状态矩阵，调参改这里
├── STRATEGY_GUIDE.md            ★ 本文档
│
├── data/                        ← 数据层：从通达信读取，写入 SQLite
│   ├── manager.py               DataManager —— 启动自动同步，之后纯读DB
│   ├── tdx_sync.py              通达信 vipdoc → SQLite 增量同步器
│   ├── industry_data.py         行业板块数据接口
│   └── stock_data.py            个股成分股接口
│
├── filters/                     ← 筛选层：大盘→行业→个股 三层管道
│   ├── market_filter.py         Layer 1: 大盘评分卡（A/B/C/D 等级）
│   ├── industry_filter.py       Layer 2: 行业筛选 + 回调 + 趋势初现
│   └── stock_filter.py          Layer 3: 个股7项检查（覆盖主板+创业板+科创板）
│
├── indicators/                  ← 指标库：30+ 独立函数，全部可单独调用
│   ├── strategies.py            ★ 统一策略入口（22个可调参函数 + full_review）
│   ├── multi_timeframe.py       三时间尺度趋势评估（道氏框架核心）
│   ├── trend_strength.py        ADX、均线排列、斜率、趋势初现、回调检测
│   ├── price_structure.py       波段高低点 Zigzag + HH/HL 结构
│   ├── trend_quality.py         震荡过滤、假突破验证、见顶、加速
│   ├── exit_signals.py          吊灯止损、ATR移动止损、均线止盈
│   ├── patterns.py              10种形态识别（头肩/双顶底/V/圆/三角/楔形）
│   ├── bollinger.py             布林带收缩/扩张
│   ├── relative_strength.py     横截面 RS 排名
│   ├── rotation.py              行业轮动信号
│   ├── market_breadth.py        涨跌家数、市场宽度
│   └── volume_analysis.py       量价配合分析
│
├── output/                      ← 输出：日志 + 报告
│   ├── screener_YYYYMMDD.log   每日完整日志（追加写入）
│   ├── result_YYYYMMDD.txt     每日关键结果摘要
│   ├── console.py              终端彩色输出
│   └── report.py               Markdown 报告生成
│
├── utils/
│   └── logger.py                双通道日志（终端 + 文件）
│
├── tdx_importer.py              首次导入工具：通达信 .day → DB
├── tdx_industry_import.py       首次导入工具：mootdx 板块 → DB
├── batch_download.py            已废弃（baostock 不可用）
└── trend_data.db                SQLite 数据库（941万行）
```

### 依赖

```
mootdx          # 读通达信板块指数
pandas, numpy   # 数据处理
sqlite3         # 本地数据库（Python 内置）
```

无需网络，无需 akshare/tushare/baostock。

---

## 使用方法

### 一、日常使用（命令行）

```bash
# 完整分析：自动同步 → 大盘 → 行业 → 个股
python main.py

# 只看大盘
python main.py --market-only

# 详细输出 + 生成 Markdown 报告
python main.py --verbose --report
```

**启动流程**：每次运行自动检查通达信是否有新数据 → 有则增量导入（~20s），无则秒级跳过 → 运行三层次分析。

**覆盖范围**：
- 个股：沪深主板(60/00) + 创业板(30/301) + **科创板(68)**，约 5000+ 只
- 指数：上证/深证/沪深300/中证500/创业板指等 18 个
- 行业：通达信 655 个板块（行业+概念+地域+风格）

### 二、策略研究（Python API）

```python
from data.manager import DataManager
from indicators.strategies import *

dm = DataManager()          # 自动同步 + 连接DB

# --- 大盘分析 ---
idx = dm.get_index_daily("000300")
osc = oscillation_filter(idx)        # 震荡？→ should_avoid
trend = trend_three_timeframe(idx)   # 三尺度趋势 → state="主升浪"?
exh = exhaustion_signal(idx)         # 见顶？→ level 0-3
env = market_environment(dm)         # 市场宽度 + 布林带

# --- 行业分析 ---
from filters.industry_filter import IndustryFilter
inf = IndustryFilter(dm)
top20 = inf.filter(top_n=20)                    # Top 20 强势行业
pbs = inf.get_pullback_industries(top20)        # 回调买点行业
ems = inf.get_emergence_industries(top20)       # 刚启动的行业

# --- 个股分析 ---
df = dm.get_stock_daily("688001")  # 科创板示例
review = full_review(df, dm=dm, symbol="688001", name="华兴源创")
print(review["recommendation"])    # 强烈推荐/可以关注/观望/回避
print(review["adx"]["strength"])   # 强趋势/弱趋势/震荡

# --- 止损位计算 ---
x = exit_strategy(df, entry_price=25.0)
print(x["stop_prices"])            # {chandelier, atr_trailing, ma_exit}
print(x["should_exit"])            # True/False

# --- 形态识别 ---
from indicators.patterns import detect_all_patterns
pats = detect_all_patterns(df)
print(pats)  # 头肩顶/双底/三角形/...

# --- 调参示例 ---
oscillation_filter(idx, adx_threshold=25)       # 保守
oscillation_filter(idx, adx_threshold=18)       # 激进
```

### 三、批量跑行业

```python
dm = DataManager()
boards = dm.get_industry_boards()

results = []
for b in boards:
    df = dm.get_industry_daily(b["code"])
    if df is None or len(df) < 120:
        continue
    t = trend_three_timeframe(df)
    results.append({
        "code": b["code"], "name": b["name"],
        "state": t["state"], "score": t["total_score"],
    })

# 筛选主升浪行业
bullish = [r for r in results if r["state"] == "主升浪"]
bullish.sort(key=lambda x: x["score"], reverse=True)
for r in bullish[:10]:
    print(f"{r['name']}: {r['score']:.3f}")
```

---

## 目录

1. [项目结构](#项目结构)
2. [使用方法](#使用方法)
3. [策略分类与索引](#策略分类与索引)
4. [A. 趋势识别](#a-趋势识别)
5. [B. 趋势质量](#b-趋势质量)
6. [C. 趋势阶段](#c-趋势阶段)
7. [D. 形态识别](#d-形态识别)
8. [E. 相对强度](#e-相对强度)
9. [F. 市场环境](#f-市场环境)
10. [G. 退出管理](#g-退出管理)
11. [H. 行业轮动](#h-行业轮动)
12. [I. 量价分析](#i-量价分析)
13. [综合复盘](#综合复盘)
14. [参数调优指南](#参数调优指南)
15. [大师建议：每日复盘流程](#大师建议每日复盘流程)

---

## 快速开始

```python
from indicators.strategies import full_review

# 对任意标的运行全部策略
review = full_review(stock_df, symbol="600519", name="贵州茅台")

print(review["recommendation"])   # 强烈推荐 / 可以关注 / 观望 / 回避
print(review["composite_score"])  # 综合评分
```

---

## 策略分类与索引

| 类别 | 函数 | 作用 | 返回 |
|------|------|------|------|
| A-趋势识别 | `trend_three_timeframe` | 道氏三层趋势综合评估 | state: 主升浪/回调/... |
| A-趋势识别 | `adx_trend_strength` | ADX趋势强度 | strength: 强/弱/震荡 |
| A-趋势识别 | `ma_alignment` | 均线多头排列评分 | state: 强多头/交织/... |
| A-趋势识别 | `price_structure` | HH/HL波段结构 | is_bullish: True/False |
| B-趋势质量 | `oscillation_filter` | 震荡市过滤 | should_avoid: True/False |
| B-趋势质量 | `breakout_quality` | 突破真伪验证 | is_valid_breakout |
| C-趋势阶段 | `exhaustion_signal` | 见顶衰竭检测 | level: 0-3, signals[] |
| C-趋势阶段 | `acceleration_signal` | 加速赶顶/底检测 | is_accelerating |
| C-趋势阶段 | `pullback_or_reversal` | 回调 vs 反转 | classification |
| C-趋势阶段 | `trend_emergence` | 趋势初现检测 | is_emerging |
| D-形态识别 | `chart_patterns` | 10种经典形态 | patterns{} |
| E-相对强度 | `relative_strength` | 横截面RS排名 | {code: rs_score} |
| F-市场环境 | `market_environment` | 大盘宽度+波动率 | is_healthy |
| G-退出管理 | `exit_strategy` | 三种止损/止盈 | should_exit, reasons |
| H-行业轮动 | `sector_rotation` | 板块强弱转换 | strengthening[] |
| I-量价分析 | `volume_analysis` | 量价配合检查 | is_healthy |

---

## A. 趋势识别

### A1. `trend_three_timeframe(df, primary_weight=0.50, secondary_weight=0.30, minor_weight=0.20)`

**技术原理**：道氏理论认为市场同时存在三种趋势——主要趋势(数月~年)、次级趋势(数周~月)、小型趋势(数天~周)。通过对三个时间尺度独立评分后加权合成，同时用状态矩阵将 (prim_up, sec_up, min_up) 三元组映射到8种交易状态。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| primary_weight | 0.50 | 主要趋势权重。长线投资者可调高至0.60 |
| secondary_weight | 0.30 | 次级趋势权重 |
| minor_weight | 0.20 | 小型趋势权重。短线交易者可调高至0.35 |

**返回关键字段**：`state`(主升浪/小回调/中级回调/回调结束/熊市反弹/反弹衰竭/短期异动/全面弱势)、`action`(LONG_FULL/LONG_HOLD/LONG_ENTRY/WAIT/NO_TRADE)、`total_score`(0~1)

### A2. `adx_trend_strength(df, period=14, strong_threshold=25, weak_threshold=20)`

**技术原理**：ADX由Welles Wilder提出，衡量趋势强度而不指示方向。ADX不关心价格涨跌，只关心价格是否在"有方向性地移动"。+DI与-DI的关系指示方向。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| period | 14 | ADX计算周期。Wilder原始值。越小越敏感 |
| strong_threshold | 25 | 强趋势阈值。ADX>25确认趋势有效 |
| weak_threshold | 20 | 震荡阈值。ADX<20绝对不用趋势策略 |

### A3. `ma_alignment(df, ma_periods=(5,10,20,60,120), window=40)`

**技术原理**：均线排列是趋势最直观的表达。统计window天内短周期均线>长周期均线的天数占比，输出-1~+1的连续评分。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| ma_periods | (5,10,20,60,120) | 覆盖短中长期的均线组合 |
| window | 40 | 统计窗口。越大越平滑，越小越及时 |

### A4. `price_structure(df, swing_threshold=0.04, min_swings=2)`

**技术原理**：道氏理论最基础原理——上升趋势=HH+HL。使用简化Zigzag算法识别波段极值。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| swing_threshold | 0.04(4%) | 反转确认阈值。3%更敏感但假信号多；5%更可靠但滞后 |
| min_swings | 2 | 最少几轮HH+HL算有效趋势 |

---

## B. 趋势质量

### B1. `oscillation_filter(df, adx_period=20, adx_threshold=20, consecutive_days=3)`

**技术原理**：趋势策略在震荡市中会反复被止损，是最大亏损来源。ADX<20 且 ±DI频繁交叉=无趋势环境，应绝对避免使用趋势策略。这是量化趋势跟踪领域最基础的过滤规则。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| adx_threshold | 20 | 震荡判定线。提高到25更保守 |
| consecutive_days | 3 | ADX需持续低于阈值的确认天数 |

### B2. `breakout_quality(df, volume_ratio=1.5, close_confirm_days=2, ma_period=20)`

**技术原理**：假突破(Bull/Bear Trap)是最常见的亏损来源。"量在价先"——真正的突破必须有成交量确认+连续收盘站稳。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| volume_ratio | 1.5 | 突破日量需>N日均量的倍数。大盘股可用1.3，小盘股建议1.8 |
| close_confirm_days | 2 | 需连续站稳的天数 |
| ma_period | 20 | 用作默认关键位的均线 |

---

## C. 趋势阶段

### C1. `exhaustion_signal(df, lookback=60, adx_peak_threshold=35, adx_decline=8, volume_decline_pct=0.20, stagnation_range=0.03)`

**技术原理**：趋势不会突然结束，会有衰竭信号。综合四个维度：量价背离(最可靠)、ADX从高位回落、放量滞涨(主力出货)、HL失败(道氏反转确认)。level 0=无信号，3=强警告。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| lookback | 60 | 回看天数 |
| adx_peak_threshold | 35 | ADX需>此值才算"高位"。波动大的标的可提到40 |
| adx_decline | 8 | ADX下降幅度触发警告 |
| volume_decline_pct | 0.20 | 量缩比例阈值。蓝筹可放宽到0.25 |
| stagnation_range | 0.03(3%) | 放量滞涨的振幅阈值 |

### C2. `acceleration_signal(df, short_window=5, mid_window=20, accel_ratio_threshold=1.8, vol_ratio_threshold=1.3)`

**技术原理**：趋势末端往往出现加速——斜率陡增+成交量暴增。这是最后的情绪驱动，利润最丰厚但也最危险。加速段出现后应收紧止损。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| accel_ratio_threshold | 1.8 | 短期涨速/中期涨速阈值。>1.8=加速 |
| vol_ratio_threshold | 1.3 | 短期量/中期量阈值 |

### C3. `pullback_or_reversal(df, use_primary_trend=True, low_broken_threshold=0.98, rebound_strength_threshold=0.85)`

**技术原理**：趋势交易最核心判断——当前下跌是回调还是反转。回调=长期趋势完好，是加仓机会；反转=道氏低点被跌破，应退出。判定依据：是否跌破前一个显著低点+均线是否空头排列+ADX动态变化。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| low_broken_threshold | 0.98 | 跌破前低2%以上判定为HL失败 |
| rebound_strength_threshold | 0.85 | 反弹<前高85%判定为弱势 |

### C4. `trend_emergence(df, adx_period=20, adx_threshold=20, lookback=5)`

**技术原理**：捕捉趋势的"启动瞬间"——ADX上穿阈值 + 价格站上均线。趋势启动初期是风险收益比最佳的位置。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| adx_threshold | 20 | ADX上穿突破此值触发信号 |
| lookback | 5 | 上穿发生在此天数内有效 |

---

## D. 形态识别

### `chart_patterns(df)`

**技术原理**：经典技术形态是市场心理的可视化呈现。自动检测10种形态：
- **反转形态**：头肩顶/底、双顶/底、V顶/底、圆顶/底
- **持续形态**：对称三角形、上升三角形、下降三角形、上升楔形、下降楔形

无额外参数。形态检测基于波段高低点的几何特征。

---

## E. 相对强度

### `relative_strength(all_returns_dict, periods=(20,40,60))`

**技术原理**：RS排名衡量标的在所有同类中的相对位置。RS>0.8表示处于同类前20%，是真正强势的标的。多周期综合评估避免单一周期噪音。

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| periods | (20,40,60) | 评估周期组合。短线可加10，长线可加120 |

---

## F. 市场环境

### `market_environment(dm)`

**技术原理**：市场宽度(涨跌家数比)衡量参与广度——指数上涨但多数个股下跌=不可持续。布林带收缩预示即将大幅波动。

需要 DataManager 实例。无额外调参。

---

## G. 退出管理

### `exit_strategy(df, entry_price=None, chandelier_mult=3.0, atr_period=22, atr_trail_mult=2.0, ma_exit_period=20, ma_below_days=2)`

**技术原理**：
- 吊灯止损：让利润奔跑但防止大幅回吐。从N日最高价回撤M×ATR退出
- ATR移动止损：止损线只上不下，保护浮盈
- 均线止盈：简单但有效

**参数**：
| 参数 | 默认值 | 含义 |
|------|--------|------|
| chandelier_mult | 3.0 | 吊灯止损ATR倍数。大=宽松(适合长线)；小=紧凑(适合短线) |
| atr_trail_mult | 2.0 | 移动止损ATR倍数 |
| ma_exit_period | 20 | 均线止盈周期 |
| ma_below_days | 2 | 跌破MA触发止盈的天数 |

---

## H. 行业轮动

### `sector_rotation(dm, lookback_short=5, lookback_long=20, top_n=10)`

**技术原理**：A股最显著特征之一是板块轮动。计算每个行业的短期排名与长期排名的差异，差值越大说明资金轮动越剧烈。

---

## I. 量价分析

### `volume_analysis(df, window=20, healthy_ratio=1.1)`

**技术原理**：健康的上升趋势=上涨放量(需求)+下跌缩量(供给减少)。量价背离是趋势衰竭的早期信号。

---

## 综合复盘

### `full_review(df, dm=None, symbol="", name="")`

一键运行全部策略，返回完整 dict。包含 `composite_score`(综合评分) 和 `recommendation`(强烈推荐/可以关注/观望/回避)。

---

## 参数调优指南

### 敏感性调节

| 偏向 | swing_threshold | adx_threshold | volume_ratio | chandelier_mult |
|------|-----------------|---------------|--------------|-----------------|
| 激进(多信号) | 0.03 | 18 | 1.2 | 2.0 |
| 默认(平衡) | 0.04 | 20 | 1.5 | 3.0 |
| 保守(少信号) | 0.05 | 25 | 1.8 | 4.0 |

### 标的类型适配

| 标的特点 | 建议调整 |
|----------|----------|
| 大盘蓝筹(低波动) | swing_threshold=0.03, accel_ratio=1.5 |
| 中小创(高波动) | swing_threshold=0.05, chandelier_mult=3.5 |
| 行业指数 | 使用默认值即可 |
| 大盘指数 | adx_threshold=22, 更严格过滤 |

---

## 大师建议：每日复盘流程

作为趋势交易者，每日复盘的核心目的是回答三个问题：
**1) 现在该不该做？2) 在哪个方向做？3) 做哪些标的？**

### 建议采纳的 8 个核心指标

| 序号 | 指标 | 作用 | 优先级 |
|------|------|------|--------|
| 1 | `oscillation_filter` | 大盘是否震荡——决定能不能用趋势策略 | 🔴 第一关 |
| 2 | `trend_three_timeframe` | 三时间尺度趋势状态——决定多空方向 | 🔴 必看 |
| 3 | `exhaustion_signal` | 趋势是否衰竭——决定是否减仓/离场 | 🔴 必看 |
| 4 | `pullback_or_reversal` | 短期下跌是回调还是反转——决定加仓还是退出 | 🟡 交易决策 |
| 5 | `trend_emergence` | 是否有趋势刚启动的行业——寻找新机会 | 🟡 选股 |
| 6 | `adx_trend_strength` | 趋势强度量化——用于仓位管理 | 🟡 仓位 |
| 7 | `volume_analysis` | 量价是否配合——验证趋势真伪 | 🟢 辅助确认 |
| 8 | `exit_strategy` | 止损/止盈位——具体的买卖价位 | 🟢 执行 |

### 每日复盘步骤

```
Step 1: 大盘环境 (5分钟)
  ↓
  oscillation_filter(沪深300) → 震荡？→ 今天是否适合趋势策略
  trend_three_timeframe(沪深300) → 大盘三尺度趋势状态
  exhaustion_signal(沪深300) → 大盘有无见顶信号
  market_environment(dm) → 市场宽度+布林带

Step 2: 行业筛选 (10分钟)
  ↓
  对655个行业板块批量运行 trend_three_timeframe
  → 提取"主升浪"行业 → Top 10 强势行业
  → 提取"小回调"行业 → 回调买点(长期向上+短期回调)
  → 运行 sector_rotation → 资金正在流入/流出的行业
  → 运行 trend_emergence → 刚启动的行业

Step 3: 个股筛选 (15分钟)
  ↓
  在Step 2选出的强势行业中：
  → 逐个运行 full_review → 综合评分
  → 过滤: composite_score > 50 + adx.is_trending + !oscillation.should_avoid
  → 排序取 Top 20
  → 检查: chart_patterns (避开头肩顶、双顶等见顶形态)
  → 人工Review Top 5

Step 4: 持仓管理 (5分钟)
  ↓
  对已有持仓：
  → exit_strategy → 是否触发止损/止盈
  → pullback_or_reversal → 是回调还是反转
  → acceleration_signal → 是否加速(加速中收紧止损)
```

### 风险控制铁律

1. **ADX<20 绝对不交易**——震荡市用趋势策略=送钱
2. **量价背离出现时减仓**——没有量的新高不可信
3. **加速段收紧止损到 2×ATR**——加速=随时可能反转
4. **跌破前一个显著低点果断离场**——结构破坏=趋势改变
5. **单行业持仓不超过 30%**——避免同质化风险（如全部在"电子"大类）
