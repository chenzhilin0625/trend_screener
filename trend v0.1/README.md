# Trend — ROC(20) 动量排名

一个指标：**相对 20 个交易日前的涨跌幅**。用它给行业板块和个股排名。

---

## 用法

```bash
cd "trend v0.1"

# 首次下载全量数据（一次性，~19 分钟）
python download.py

# 每日增量更新
python updater.py

# 运行排名
python run.py                    # 板块 Top 15 + 个股 Top 30
python run.py --sectors          # 仅板块
python run.py --top 50           # 自定义数量
python run.py --save out.csv     # 导出
```

---

## 输出示例

```
ROC(20) 动量排名  2026-07-20 11:00
DB: trend_em.db  市值 >= 50亿

行业/概念板块 Top 15  (2.3s)
    1. 银行         +5.2%
    2. 煤炭         +3.1%
    ...

个股 ROC(20) Top 30  (35.2s)
    1. 600519 贵州茅台    白酒       +8.2%     22000
    2. 601939 建设银行    银行       +6.5%     20000
    ...

总耗时 37.5s
```

---

## 文件结构

```
trend v0.1/
├── run.py              ← CLI 入口
├── download.py          ← 全量下载
├── updater.py           ← 增量更新
├── schema.py            ← 数据库 DDL
├── engine/
│   ├── loader.py        ← SQLite → pandas
│   └── scorer.py        ← ROC(20) 打分（48 行）
├── trend_em.db          ← 1.3 GB
└── README.md
```

---

## 数据

- 东方财富公开 HTTP API，纯本地 SQLite
- 5,540 只 A 股 + 496 行业 + 495 概念板块 + 5 个大盘指数
- 日线数据从 2021-01 开始

---

## 程序化调用

```python
from engine.loader import DataLoader
from engine.scorer import score_stocks, score_sectors

loader = DataLoader()
sectors = score_sectors(loader)
stocks = score_stocks(loader, min_mcap=20e9, top_n=20)
```
